import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# --- Canonical Week-1 survival constants (from DM) ---
GRAIN_PER_CAPITA = 0.006  # 2700 / 450_000
WATER_PER_CAPITA = 0.004  # 1800 / 450_000


@dataclass
class WeekEconomyResult:
    week: int
    population: int
    grain_needed: float
    water_needed: float
    grain_produced: int
    water_produced: int
    survival_ratio: float
    gross_value: float
    tax_rate: float
    tax_income: float
    player_share: float
    player_payout: float
    upkeep_total: float


# -------------------------
# Helpers
# -------------------------
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _stable_rand(week: int, key: str, a: float, b: float) -> float:
    h = hashlib.sha256(f"{week}:{key}".encode("utf-8")).hexdigest()
    seed = int(h[:8], 16)
    rng = random.Random(seed)
    return rng.uniform(a, b)


def _stable_unit_random(week: int, key: str) -> float:
    h = hashlib.sha256(f"u:{week}:{key}".encode("utf-8")).hexdigest()
    seed = int(h[:8], 16)
    rng = random.Random(seed)
    return rng.random()


def _stochastic_int(expected: float, week: int, key: str) -> int:
    """Convert small expected values into occasional 1s instead of always rounding to 0."""
    if expected <= 0:
        return 0
    base = int(expected)  # floor
    frac = expected - base
    if frac <= 0:
        return base
    return base + (1 if _stable_unit_random(week, key) < frac else 0)


def _infer_family_from_region(week: int, item_name: str, region: str) -> str:
    r = (region or "").lower().replace("’", "'")
    if "val'har" in r or "valhar" in r:
        return "valar family"
    if "val'heim" in r or "valheim" in r:
        return "valeim family"
    if "ahm'neshti" in r or "ahmneshti" in r or "neshti" in r:
        return "neshti family"
    if "ahel'man" in r or "ahelman" in r:
        return "moonshadow"
    if "new triport" in r or "triport" in r:
        return "lathien"
    if "moonglade" in r:
        choices = ["eladrin", "elenwe", "galadhel"]
        h = hashlib.sha256(f"{week}:{item_name}:{region}".encode("utf-8")).hexdigest()
        return choices[int(h[:2], 16) % len(choices)]
    return ""


# -------------------------
# Settings + State
# -------------------------
def get_settings(sb) -> Dict[str, float]:
    """Read economy settings. Extra fields are optional; sensible defaults keep Week 1 near ~75gp payout."""
    r = (
        sb.table("economy_settings")
        .select("tax_rate,player_share,rand_min,rand_max,economy_scale,war_severity,price_elasticity,baseline_price_index,spend_gp_per_capita")
        .limit(1)
        .execute()
    )

    # Defaults: war-time economy tuned so that with tax_rate=0.10 and player_share=0.10,
    # payout is ~75 gp at population 450k when regions are in poor condition.
    defaults = {
        "tax_rate": 0.10,
        "player_share": 0.10,           # players get 10% of taxes (1% of total economy)
        "rand_min": 0.90,
        "rand_max": 1.10,
        # economy_scale remains supported but is treated as a *volume* factor (not a GDP dial)
        "economy_scale": 1.0,
        # war severity 0..1; 1 = heavy war (low volume, high scarcity)
        "war_severity": 1.0,
        # how strongly lower prices increase total volume (0 = none, 1 = strong)
        "price_elasticity": 0.7,
        # expected war-time price index vs baseline (used for affordability scaling)
        "baseline_price_index": 1.8,
        # baseline spending capacity per capita per week (gp). Automated: scales with population.
        # This value is chosen so Week 1 total economy is roughly ~7,500 gp when war_severity=1.
        "spend_gp_per_capita": 0.0417,
    }

    if not r.data:
        return defaults

    row = r.data[0] or {}
    def _f(key: str, fallback: float) -> float:
        v = row.get(key)
        try:
            return float(v) if v is not None else float(fallback)
        except Exception:
            return float(fallback)

    tax_rate = _clamp(_f("tax_rate", defaults["tax_rate"]), 0.0, 1.0)
    player_share = _clamp(_f("player_share", defaults["player_share"]), 0.0, 1.0)
    rand_min = _f("rand_min", defaults["rand_min"])
    rand_max = _f("rand_max", defaults["rand_max"])
    if rand_max < rand_min:
        rand_min, rand_max = rand_max, rand_min
    rand_min = _clamp(rand_min, 0.10, 2.0)
    rand_max = _clamp(rand_max, 0.10, 3.0)

    economy_scale = _f("economy_scale", defaults["economy_scale"])
    if economy_scale <= 0:
        economy_scale = 1.0
    economy_scale = _clamp(economy_scale, 0.01, 10.0)

    war_severity = _clamp(_f("war_severity", defaults["war_severity"]), 0.0, 1.0)
    price_elasticity = _clamp(_f("price_elasticity", defaults["price_elasticity"]), 0.0, 2.0)
    baseline_price_index = _clamp(_f("baseline_price_index", defaults["baseline_price_index"]), 0.5, 5.0)
    spend_gp_per_capita = _clamp(_f("spend_gp_per_capita", defaults["spend_gp_per_capita"]), 0.0001, 5.0)

    return {
        "tax_rate": tax_rate,
        "player_share": player_share,
        "rand_min": rand_min,
        "rand_max": rand_max,
        "economy_scale": economy_scale,
        "war_severity": war_severity,
        "price_elasticity": price_elasticity,
        "baseline_price_index": baseline_price_index,
        "spend_gp_per_capita": spend_gp_per_capita,
    }


def rarity_rates(sb) -> Dict[str, float]:
    r = sb.table("rarity_prod_rates").select("rarity,prod_rate").execute()
    rates: Dict[str, float] = {}
    for row in (r.data or []):
        key = (row.get("rarity") or "").strip()
        if key:
            rates[key] = float(row.get("prod_rate") or 0)
    return rates


def get_population(sb, week: int) -> int:
    r = sb.table("population_state").select("population").eq("week", week).limit(1).execute()
    if r.data:
        return int(r.data[0]["population"])
    return 450_000


def _avg_region_prod(sb, week: int) -> float:
    try:
        rows = sb.table("region_week_state").select("production_score").eq("week", week).execute().data or []
        if not rows:
            return 0.0
        vals = [float(r.get("production_score") or 0) for r in rows]
        return sum(vals) / max(1, len(vals))
    except Exception:
        return 0.0


def _avg_family_rep(sb, week: int) -> float:
    try:
        rows = sb.table("family_week_state").select("reputation_score").eq("week", week).execute().data or []
        if not rows:
            return 0.0
        vals = [float(r.get("reputation_score") or 0) for r in rows]
        return sum(vals) / max(1, len(vals))
    except Exception:
        return 0.0


def region_multiplier(sb, week: int, region: str) -> float:
    r = (
        sb.table("region_week_state")
        .select("production_score,dm_modifier")
        .eq("week", week)
        .eq("region", region)
        .limit(1)
        .execute()
    )
    if not r.data:
        return 1.0
    row = r.data[0]
    ps = float(row.get("production_score") or 0)
    dm = float(row.get("dm_modifier") or 0)
    mult = 1.0 + (ps * 0.05) + dm
    return _clamp(mult, 0.50, 1.75)


def family_multiplier(sb, week: int, family: str) -> float:
    r = (
        sb.table("family_week_state")
        .select("reputation_score,dm_modifier")
        .eq("week", week)
        .eq("family", family)
        .limit(1)
        .execute()
    )
    if not r.data:
        return 1.0
    row = r.data[0]
    rep = float(row.get("reputation_score") or 0)
    dm = float(row.get("dm_modifier") or 0)
    mult = 1.0 + (rep * 0.03) + dm
    return _clamp(mult, 0.50, 1.75)


# -------------------------
# Core Economy
# -------------------------
def _tier_weight(tier: int, rarity: str) -> float:
    # Prefer tier when available; fallback to rarity.
    if tier == 1:
        return 1.0
    if tier == 2:
        return 0.35
    if tier == 3:
        return 0.12
    if tier == 4:
        return 0.05
    if tier == 5:
        return 0.02

    r = (rarity or "").strip().lower()
    if r == "common":
        return 1.0
    if r == "uncommon":
        return 0.35
    if r == "rare":
        return 0.12
    if r == "very rare":
        return 0.05
    if r == "legendary":
        return 0.02
    return 0.25


def compute_week_economy(sb, week: int) -> Tuple[WeekEconomyResult, List[Dict[str, Any]]]:
    """Automated economy:
    - Total volume scales with population and war severity.
    - Prices are high during war, and fall as regions/families improve.
    - Lower prices increase total sales volume (price elasticity).
    - Output is distributed across items by tier/rarity weights.
    """
    settings = get_settings(sb)
    rates = rarity_rates(sb)

    pop = get_population(sb, week)
    grain_needed = pop * GRAIN_PER_CAPITA
    water_needed = pop * WATER_PER_CAPITA

    rand_min, rand_max = settings["rand_min"], settings["rand_max"]

    # War-time scarcity + recovery from regional/familial state
    avg_prod = _avg_region_prod(sb, week)
    avg_rep = _avg_family_rep(sb, week)

    # Volume recovers with production + reputation.
    recovery_factor = _clamp(1.0 + (avg_prod * 0.08) + (avg_rep * 0.05), 0.25, 2.0)

    # Scarcity pushes prices up during war; easing with recovery.
    war_sev = settings["war_severity"]
    scarcity_mult = _clamp(1.0 + 1.2 * war_sev, 1.0, 2.8)  # 1.0..2.8
    scarcity_mult *= _clamp(1.0 - (avg_prod * 0.05) - (avg_rep * 0.03), 0.6, 1.2)

    # Base spending capacity per capita, automatically scales with population.
    spend_pc = settings["spend_gp_per_capita"]
    # War reduces volume (production low). economy_scale is an extra global dial (keep near 1).
    war_volume_mult = _clamp(1.0 - 0.6 * war_sev, 0.25, 1.0)
    global_volume = settings["economy_scale"] * war_volume_mult * recovery_factor

    # Load items
    items = (
        sb.table("gathering_items")
        .select("name,profession,tier,rarity,base_price_gp,vendor_price_gp,sale_price_gp,region,family,is_special")
        .execute()
        .data
        or []
    )

    per_item: List[Dict[str, Any]] = []
    gross_value = 0.0
    grain_produced = 0
    water_produced = 0

    # First pass: compute effective price and weights, and build a price index
    weighted_price_index_num = 0.0
    weighted_price_index_den = 0.0
    prepared: List[Dict[str, Any]] = []

    for it in items:
        name = (it.get("name") or "").strip()
        if not name:
            continue

        rarity = (it.get("rarity") or "Common").strip()
        tier = int(it.get("tier") or 1)
        region = (it.get("region") or "").strip()
        family = (it.get("family") or "").strip()

        if not family and region:
            family = _infer_family_from_region(week, name, region)

        rm = region_multiplier(sb, week, region) if region else 1.0
        fm = family_multiplier(sb, week, family) if family else 1.0

        # Price: base_price_gp preferred, fallback to vendor/sale
        raw_price = it.get("base_price_gp") or it.get("vendor_price_gp") or it.get("sale_price_gp") or 0
        base_price = float(raw_price or 0)

        # Better regions/families: cheaper goods (inverse of production multipliers), but still clamped.
        local_price_mult = 1.0 / _clamp(rm * fm, 0.60, 1.80)

        effective_price = max(0.0, base_price * scarcity_mult * local_price_mult)

        # Weight determines share of *transactions* (not raw output)
        w = _tier_weight(tier, rarity)

        # Survival goods: always counted, but treated separately for quantities
        nlow = name.lower().replace("’", "'")
        is_water = nlow in {"moonwell water", "moonwell water (t1)", "water"} or nlow.startswith("moonwell water")
        is_grain = nlow in {"lunar grain", "lunar grain (t1)", "grain"} or nlow.startswith("lunar grain")

        prepared.append(
            {
                "name": name,
                "rarity": rarity,
                "tier": tier,
                "region": region,
                "family": family,
                "rm": rm,
                "fm": fm,
                "effective_price": float(effective_price),
                "weight": float(w),
                "is_water": is_water,
                "is_grain": is_grain,
            }
        )

        # Price index: compare effective price to base price (avoid division by zero)
        if base_price > 0 and not (is_water or is_grain):
            weighted_price_index_num += (effective_price / base_price) * w
            weighted_price_index_den += w

    price_index = (weighted_price_index_num / weighted_price_index_den) if weighted_price_index_den else scarcity_mult
    baseline_price_index = settings["baseline_price_index"]
    elasticity = settings["price_elasticity"]

    # Lower prices -> higher volume. Higher prices -> lower volume.
    affordability = (baseline_price_index / max(0.05, price_index)) ** elasticity
    affordability = _clamp(affordability, 0.25, 2.5)

    # Automated total "sales volume" budget (gp): depends on population, prices, war, recovery.
    total_budget_gp = pop * spend_pc * global_volume * affordability

    # Split budget: always reserve a portion for survival goods (war-time reality)
    survival_budget_share = _clamp(0.35 + 0.10 * war_sev, 0.25, 0.55)  # war -> more spend on essentials
    survival_budget = total_budget_gp * survival_budget_share
    market_budget = total_budget_gp - survival_budget

    # Survival quantities (do not use spend budget to determine survival quantities; use needs + war/recovery)
    # Production is low during war; as recovery grows, it approaches need.
    survival_supply_factor = _clamp(0.55 - 0.25 * war_sev + 0.20 * (recovery_factor - 1.0), 0.15, 1.10)
    grain_produced = int(round(grain_needed * survival_supply_factor))
    water_produced = int(round(water_needed * survival_supply_factor))

    # Compute survival value using average prices for grain/water items if present
    grain_price = None
    water_price = None
    for p in prepared:
        if p["is_grain"] and p["effective_price"] > 0:
            grain_price = p["effective_price"]
            break
    for p in prepared:
        if p["is_water"] and p["effective_price"] > 0:
            water_price = p["effective_price"]
            break
    grain_price = float(grain_price or 1.0)
    water_price = float(water_price or 1.0)

    gross_value += grain_produced * grain_price
    gross_value += water_produced * water_price

    # Distribute market budget across non-survival items by weights
    market_items = [p for p in prepared if not (p["is_water"] or p["is_grain"])]
    total_w = sum(p["weight"] for p in market_items) or 1.0

    for p in market_items:
        name = p["name"]
        w = p["weight"]
        region = p["region"]
        family = p["family"]
        rarity = p["rarity"]
        eff_price = float(p["effective_price"] or 0.0)

        rf = _stable_rand(week, name, rand_min, rand_max)

        item_budget = market_budget * (w / total_w) * rf

        # If eff_price is 0, value can't be computed; skip safely.
        if eff_price <= 0:
            qty = 0
            value = 0.0
        else:
            expected_qty = item_budget / eff_price
            qty = _stochastic_int(expected_qty, week, f"{name}|{region}|{family}|{rarity}")
            value = qty * eff_price

        gross_value += value

        per_item.append(
            {
                "week": week,
                "item_name": name,
                "qty": int(qty),
                "effective_price": float(eff_price),
                "gross_value": float(value),
                "rarity": rarity,
                "region": region,
                "family": family,
            }
        )

    # Add explicit survival rows (so week output matches summary)
    per_item.append(
        {
            "week": week,
            "item_name": "Lunar Grain",
            "qty": int(grain_produced),
            "effective_price": float(grain_price),
            "gross_value": float(grain_produced * grain_price),
            "rarity": "Common",
            "region": "Moonglade City",
            "family": "eladrin",
        }
    )
    per_item.append(
        {
            "week": week,
            "item_name": "Moonwell Water",
            "qty": int(water_produced),
            "effective_price": float(water_price),
            "gross_value": float(water_produced * water_price),
            "rarity": "Common",
            "region": "Moonglade City",
            "family": "eladrin",
        }
    )

    grain_ratio = (grain_produced / grain_needed) if grain_needed else 1.0
    water_ratio = (water_produced / water_needed) if water_needed else 1.0
    survival_ratio = min(grain_ratio, water_ratio)

    tax_rate = settings["tax_rate"]
    tax_income = gross_value * tax_rate
    player_share = settings["player_share"]
    player_payout = tax_income * player_share

    summary = WeekEconomyResult(
        week=week,
        population=int(pop),
        grain_needed=float(grain_needed),
        water_needed=float(water_needed),
        grain_produced=int(grain_produced),
        water_produced=int(water_produced),
        survival_ratio=float(survival_ratio),
        gross_value=float(gross_value),
        tax_rate=float(tax_rate),
        tax_income=float(tax_income),
        player_share=float(player_share),
        player_payout=float(player_payout),
        upkeep_total=0.0,
    )

    return summary, per_item


def write_week_economy(sb, summary: WeekEconomyResult, per_item_rows: List[Dict[str, Any]]):
    # Replace per-item output for that week
    sb.table("economy_week_output").delete().eq("week", summary.week).execute()
    if per_item_rows:
        chunk = 250
        for i in range(0, len(per_item_rows), chunk):
            sb.table("economy_week_output").insert(per_item_rows[i : i + chunk]).execute()

    sb.table("economy_week_summary").upsert(
        {
            "week": summary.week,
            "population": summary.population,
            "grain_needed": summary.grain_needed,
            "water_needed": summary.water_needed,
            "grain_produced": summary.grain_produced,
            "water_produced": summary.water_produced,
            "survival_ratio": summary.survival_ratio,
            "gross_value": summary.gross_value,
            "tax_rate": summary.tax_rate,
            "tax_income": summary.tax_income,
            "player_share": summary.player_share,
            "player_payout": summary.player_payout,
        },
        on_conflict="week",
    ).execute()
