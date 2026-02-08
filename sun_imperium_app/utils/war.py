from dataclasses import dataclass


# Rock-paper-scissors modifiers
# guardians > archers > mages > guardians
TYPE_ADVANTAGE = {
    ("guardian", "archer"): 1.25,
    ("archer", "mage"): 1.25,
    ("mage", "guardian"): 1.25,
}


def matchup_multiplier(attacker: str, defender: str) -> float:
    if attacker == defender:
        return 1.0
    return TYPE_ADVANTAGE.get((attacker, defender), 1.0)


@dataclass
class Force:
    guardians: int
    archers: int
    mages: int
    clerics: int
    others: int  # everything neutral


@dataclass
class BattleResult:
    winner: str  # "ally" or "enemy"
    ally_remaining: Force
    enemy_remaining: Force
    ally_casualties: Force
    enemy_casualties: Force
    ally_power: float
    enemy_power: float


from typing import Optional


def compute_power(force: Force, *, vs: Optional[Force] = None) -> float:
    """Compute effective power.

    Base weights:
      guardian=3, archer=2.5, mage=3, others=2, cleric=1

    Clerics provide a buff to other units: +5% per cleric up to +30%.

    RPS advantage applied by assuming a matchup against enemy composition.
    """
    base = {
        "guardian": 3.0,
        "archer": 2.5,
        "mage": 3.0,
        "others": 2.0,
        "cleric": 1.0,
    }

    buff = min(0.30, 0.05 * max(0, force.clerics))

    # If vs is provided, apply advantage multipliers based on enemy composition share.
    def weighted_mult(unit_type: str) -> float:
        if vs is None:
            return 1.0
        total_enemy = max(1, vs.guardians + vs.archers + vs.mages + vs.clerics + vs.others)
        shares = {
            "guardian": vs.guardians / total_enemy,
            "archer": vs.archers / total_enemy,
            "mage": vs.mages / total_enemy,
            "others": vs.others / total_enemy,
            "cleric": vs.clerics / total_enemy,
        }
        # expected multiplier against a mixed enemy
        m = 0.0
        for enemy_type, share in shares.items():
            m += matchup_multiplier(unit_type, enemy_type) * share
        return m

    g = force.guardians * base["guardian"] * weighted_mult("guardian")
    a = force.archers * base["archer"] * weighted_mult("archer")
    m = force.mages * base["mage"] * weighted_mult("mage")
    o = force.others * base["others"] * weighted_mult("others")
    c = force.clerics * base["cleric"]

    core = (g + a + m + o) * (1.0 + buff) + c
    return core


def clamp_force_min_one(force: Force) -> Force:
    total = force.guardians + force.archers + force.mages + force.clerics + force.others
    if total <= 0:
        # ensure at least one "other" survives
        return Force(guardians=0, archers=0, mages=0, clerics=0, others=1)
    return force


def apply_casualties(force: Force, casualty_rate: float) -> tuple[Force, Force]:
    """Applies casualties across unit buckets proportionally.

    casualty_rate in [0, 0.95]. We cap so we never wipe to 0.
    """
    casualty_rate = max(0.0, min(0.95, casualty_rate))

    def lose(n: int) -> int:
        return int(round(n * casualty_rate))

    lost = Force(
        guardians=lose(force.guardians),
        archers=lose(force.archers),
        mages=lose(force.mages),
        clerics=lose(force.clerics),
        others=lose(force.others),
    )

    rem = Force(
        guardians=max(0, force.guardians - lost.guardians),
        archers=max(0, force.archers - lost.archers),
        mages=max(0, force.mages - lost.mages),
        clerics=max(0, force.clerics - lost.clerics),
        others=max(0, force.others - lost.others),
    )

    # Ensure not fully wiped
    rem = clamp_force_min_one(rem)

    # Recompute lost if we clamped (so totals add up)
    lost = Force(
        guardians=max(0, force.guardians - rem.guardians),
        archers=max(0, force.archers - rem.archers),
        mages=max(0, force.mages - rem.mages),
        clerics=max(0, force.clerics - rem.clerics),
        others=max(0, force.others - rem.others),
    )

    return rem, lost


def simulate_battle(ally: Force, enemy: Force) -> BattleResult:
    """Deterministic battle sim.

    - Winner determined by effective power.
    - Casualty rates depend on power ratio.
      * Winner casualty: 5%..35%
      * Loser casualty: 35%..95%
    - Never 0 survivors.
    """
    ally_p = compute_power(ally, vs=enemy)
    enemy_p = compute_power(enemy, vs=ally)

    # Avoid division blowups
    ratio = (ally_p + 1e-6) / (enemy_p + 1e-6)

    if ratio >= 1.0:
        winner = "ally"
        win_ratio = min(5.0, ratio)
        lose_ratio = 1.0 / win_ratio
    else:
        winner = "enemy"
        win_ratio = min(5.0, 1.0 / ratio)
        lose_ratio = 1.0 / win_ratio

    # Map win_ratio (1..5) to casualty rates
    # closer fight -> higher casualties on both sides
    # stomp -> low winner casualties, high loser casualties
    # Linear mapping tuned for playability
    def lerp(a: float, b: float, t: float) -> float:
        return a + (b - a) * t

    t = (min(5.0, max(1.0, win_ratio)) - 1.0) / 4.0  # 0..1

    winner_cas = lerp(0.35, 0.05, t)
    loser_cas = lerp(0.35, 0.95, t)

    if winner == "ally":
        ally_rem, ally_lost = apply_casualties(ally, winner_cas)
        enemy_rem, enemy_lost = apply_casualties(enemy, loser_cas)
    else:
        ally_rem, ally_lost = apply_casualties(ally, loser_cas)
        enemy_rem, enemy_lost = apply_casualties(enemy, winner_cas)

    return BattleResult(
        winner=winner,
        ally_remaining=ally_rem,
        enemy_remaining=enemy_rem,
        ally_casualties=ally_lost,
        enemy_casualties=enemy_lost,
        ally_power=ally_p,
        enemy_power=enemy_p,
    )
