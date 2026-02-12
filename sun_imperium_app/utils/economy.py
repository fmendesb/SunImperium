import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

# --- Canonical Week-1 constants (from DM) ---
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


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _stable_seed(week: int, key: str) -> int:
    h = hashlib.sha256(f"{week}:{key}".encode("utf-8")).hexdigest()
    return int(h[:8], 16)


def _stable_rand(week: int, key: str, a: float, b: float) -> float:
    rng = random.Random(_stable_seed(week, key))
    return rng.uniform(a, b)


def _stable_unit_random(week: int, key: str) -> float:
    rng = random.Random(_stable_seed(week, f"u:{key}"))
    return rng.random()


def _stochastic_int(expected: float, week: int, key: str) -> int:
    """Convert an expected float to an int without rounding everything to 0."""
    if expected <= 0:
        return 0
    base = int(expected)  # floor
    frac = expected - base
    if frac <= 0:
        return base
    return base + (1 if _stable_unit_random(week, key) < frac else 0)


def _safe_single(sb, table: str, select_cols: str, where: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort .single() wrapper with graceful fallback."""
    q = sb.table(table).select(select_cols)
    for k, v in where.items():
        q = q.eq(k, v)
    try:
        r = q.single().execute()
        return r.data or {}
    except Exception:
        try:
            r = q.limit(1).execute()
            return (r.data or [{}])[0] or {}
        except Exception:
            return {}


def get_settings(sb) -> Dict[str, float]:
    """Read economy settings.

    Important: prefer canonical id=1 row (prevents roulette if multiple rows exist).
    Falls back to the first row if the schema doesn't have `id` yet.
    """

    defaults: Dict[str, float] = {
        "tax_rate": 0.10,
        "player_share": 0.10,
        "economy_scale": 1.0,  # war-time volume baseline multiplier
        "rand_min": 0.90,
        "rand_max": 1.10,
        # War economy knobs (automated, but still configurable)
        "war_severity": 1.0,  # 0 peace, 1 full war
        "price_elasticity": 1.3,  # lower prices -> higher volume
        "spend_per_capita": 0.015,  # will be auto-calibrated on week 1
        "target_player_payout": 75.0,
        "baseline_price_index": 10.0,  # set during calibration
        "calibrated": 0.0,  # bool stored as numeric fallback
    }

    row: Dict[str, Any] = {}

    # Try canonical id=1
    try:
        row = _safe_single(
            sb,
            "economy_settings",
            "id,tax_rate,player_share,economy_scale,rand_min,rand_max,war_severity,price_elasticity,spend_per_capita,target_player_payout,baseline_price_index,calibrated",
            {"id": 1},
        )
    except Exception:
        row = {}

    # Fallback to first row
    if not row:
        try:
            r = (
                sb.table("economy_settings")
                .select(
                    "tax_rate,player_share,economy_scale,rand_min,rand_max,war_severity,price_elasticity,spend_per_capita,target_player_payout,baseline_price_index,calibrated"
                )
                .limit(1)
                .execute()
            )
            if r.data:
                row = r.data[0] or {}
        except Exception:
            row = {}

    def f(key: str) -> float:
        return float(row.get(key) if row.get(key) is not None else defaults[key])

    tax_rate = _clamp(f("tax_rate"), 0.0, 1.0)
    player_share = _clamp(f("player_share"), 0.0, 1.0)
    economy_scale = _clamp(f("economy_scale"), 0.0001, 10.0)

    rand_min = f("rand_min")
    rand_max = f("rand_max")
    if rand_max < rand_min:
        rand_min, rand_max = rand_max, rand_min
    rand_min = _clamp(rand_min, 0.10, 2.0)
    rand_max = _clamp(rand_max, 0.10, 3.0)

    war_severity = _clamp(f("war_severity"), 0.0, 1.0)
    price_elasticity = _clamp(f("price_elasticity"), 0.0, 4.0)

    spend_per_capita = f("spend_per_capita")
    if spend_per_capita <= 0:
        spend_per_capita = defaults["spend_per_capita"]

    target_player_payout = max(0.0, f("target_player_payout"))
    baseline_price_index = max(0.0001, f("baseline_price_index"))

    calibrated_raw = row.get("calibrated")
    calibrated = False
    if isinstance(calibrated_raw, bool):
        calibrated = calibrated_raw
    elif calibrated_raw is not None:
        calibrated = bool(float(calibrated_raw))

    return {
        "tax_rate": tax_rate,
        "player_share": player_share,
        "economy_scale": economy_scale,
        "rand_min": rand_min,
        "rand_max": rand_max,
        "war_severity": war_severity,
        "price_elasticity": price_elasticity,
        "spend_per_capita": spend_per_capita,
        "target_player_payout": target_player_payout,
        "baseline_price_index": baseline_price_index,
        "calibrated": 1.0 if calibrated else 0.0,
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


def _avg_region_production(sb, week: int) -> float:
    try:
        rows = sb.table("region_week_state").select("production_score").eq("week", week).execute().data or []
        vals = [float(r.get("production_score") or 0) for r in rows]
        return sum(vals) / len(vals) if vals else 0.0
    except Exception:
        return 0.0


def _avg_family_reputation(sb, week: int) -> float:
    try:
        rows = sb.table("family_week_state").select("reputation_score").eq("week", week).execute().data or []
        vals = [float(r.get("reputation_score") or 0) for r in rows]
        return sum(vals) / len(vals) if vals else 0.0
    except Exception:
        return 0.0


def region_supply(sb, week: int, region: str) -> float:
    """Supply factor: higher production_score increases supply."""
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
    supply = 1.0 + (ps * 0.08) + dm
    return _clamp(supply, 0.50, 2.00)


def family_supply(sb, week: int, family: str) -> float:
    """Supply factor: higher family reputation increases reliability and trade access."""
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
    supply = 1.0 + (rep * 0.06) + dm
    return _clamp(supply, 0.50, 2.00)


def _tier_weight(tier: int, rarity: str) -> float:
    """Demand weight by tier and rarity. Tier dominates."""
    t = max(1, int(tier or 1))
    base = 1.0 / (t * t)
    r = (rarity or "Common").strip()
    rarity_mul = {
        "Common": 1.0,
        "Uncommon": 0.55,
        "Rare": 0.25,
        "Very Rare": 0.12,
        "Legendary": 0.05,
    }.get(r, 1.0)
    return base * rarity_mul


def _price_index(items: List[Dict[str, Any]]) -> float:
    """Compute a stable price index from common tier-1 goods."""
    candidates = [
        float(x.get("effective_price") or 0)
        for x in items
        if (x.get("tier") or 1) == 1 and (x.get("rarity") or "Common") == "Common" and float(x.get("effective_price") or 0) > 0
    ]
    if not candidates:
        candidates = [float(x.get("effective_price") or 0) for x in items if float(x.get("effective_price") or 0) > 0]
    if not candidates:
        return 1.0
    candidates.sort()
    mid = candidates[len(candidates) // 2]
    return max(0.0001, float(mid))


def _upsert_settings_patch(sb, patch: Dict[str, Any]) -> None:
    """Best-effort update to economy_settings id=1."""
    # Prefer id=1 if available
    try:
        patch_with_id = {"id": 1, **patch}
        sb.table("economy_settings").upsert(patch_with_id, on_conflict="id").execute()
        return
    except Exception:
        pass

    # Fallback: update first row (if schema doesn't have id)
    try:
        sb.table("economy_settings").update(patch).execute()
    except Exception:
        return


def compute_week_economy(sb, week: int) -> Tuple[WeekEconomyResult, List[Dict[str, Any]]]:
    """War economy model.

    Design goals:
    - Baseline week payout is ~target_player_payout (default 75) at starting conditions.
    - No manual weekly GDP input.
    - Population decreases reduce economy.
    - War: high scarcity (prices up), low volume.
    - Recovery (region production + family reputation): prices fall, volume rises, net economy increases.

    Returns (summary, per_item_rows)
    """

    settings = get_settings(sb)
    rates = rarity_rates(sb)

    pop = get_population(sb, week)
    grain_needed = pop * GRAIN_PER_CAPITA
    water_needed = pop * WATER_PER_CAPITA

    # Recovery and scarcity are global pressures derived from region/family state
    avg_prod = _avg_region_production(sb, week)
    avg_rep = _avg_family_reputation(sb, week)

    recovery_factor = _clamp(0.35 + 0.06 * avg_prod + 0.04 * avg_rep, 0.15, 1.75)

    war = settings["war_severity"]
    # scarcity: high at war, decreases with recovery
    scarcity_mult = 1.0 + (1.25 * war)
    scarcity_mult /= (0.75 + 0.25 * recovery_factor)
    scarcity_mult = _clamp(scarcity_mult, 0.80, 3.50)

    rand_min, rand_max = settings["rand_min"], settings["rand_max"]

    raw_items = (
        sb.table("gathering_items")
        .select("name,tier,rarity,base_price_gp,vendor_price_gp,sale_price_gp,region,family")
        .execute()
        .data
        or []
    )

    # First pass: compute effective prices and weights
    items: List[Dict[str, Any]] = []
    for it in raw_items:
        name = (it.get("name") or "").strip()
        if not name:
            continue

        tier = int(it.get("tier") or 1)
        rarity = (it.get("rarity") or "Common").strip() or "Common"
        region = (it.get("region") or "").strip()
        family = (it.get("family") or "").strip()

        if not family and region:
            family = _infer_family_from_region(week, name, region)

        price = it.get("base_price_gp") or it.get("vendor_price_gp") or it.get("sale_price_gp") or 0
        base_price = float(price or 0)

        # Supply improvements lower prices.
        rs = region_supply(sb, week, region) if region else 1.0
        fs = family_supply(sb, week, family) if family else 1.0
        supply = _clamp(rs * fs, 0.25, 3.0)

        effective_price = base_price * scarcity_mult / supply
        effective_price = max(0.0001, float(effective_price))

        # Demand weight: mostly tier/rarity driven
        w = _tier_weight(tier, rarity)

        items.append(
            {
                "name": name,
                "tier": tier,
                "rarity": rarity,
                "region": region,
                "family": family,
                "base_price": base_price,
                "effective_price": effective_price,
                "weight": w,
            }
        )

    # If no items, return empty economy
    if not items:
        summary = WeekEconomyResult(
            week=week,
            population=int(pop),
            grain_needed=float(grain_needed),
            water_needed=float(water_needed),
            grain_produced=0,
            water_produced=0,
            survival_ratio=0.0,
            gross_value=0.0,
            tax_rate=float(settings["tax_rate"]),
            tax_income=0.0,
            player_share=float(settings["player_share"]),
            player_payout=0.0,
            upkeep_total=0.0,
        )
        return summary, []

    # Price index and affordability
    current_index = _price_index(items)
    baseline_index = max(0.0001, float(settings["baseline_price_index"]))
    elasticity = float(settings["price_elasticity"])

    # Lower prices -> higher volume; higher prices -> lower volume.
    affordability = (baseline_index / current_index) ** elasticity
    affordability = _clamp(affordability, 0.15, 6.0)

    # War reduces volume strongly. Recovery restores.
    war_volume = _clamp(1.0 - 0.70 * war, 0.15, 1.0)

    # Base demand: population-driven spending capacity
    spend_per_capita = float(settings["spend_per_capita"])
    demand_budget = pop * spend_per_capita * war_volume * recovery_factor * affordability

    # Additional global scale (kept for DM control)
    demand_budget *= float(settings["economy_scale"])

    # Deterministic weekly noise on total demand
    demand_budget *= _stable_rand(week, "TOTAL_DEMAND", rand_min, rand_max)

    # Auto-calibrate only once: week 1 and not calibrated
    calibrated = bool(float(settings.get("calibrated", 0.0)))
    if week == 1 and not calibrated and settings["target_player_payout"] > 0:
        est_payout = demand_budget * float(settings["tax_rate"]) * float(settings["player_share"])
        if est_payout > 0:
            factor = float(settings["target_player_payout"]) / est_payout
            # Clamp so a single bad week doesn't explode calibration
            factor = _clamp(factor, 0.000001, 1000000.0)
            spend_per_capita = max(0.00000001, spend_per_capita * factor)

            _upsert_settings_patch(
                sb,
                {
                    "spend_per_capita": spend_per_capita,
                    "baseline_price_index": current_index,
                    "calibrated": True,
                },
            )

            # Recompute budget with calibrated spend
            demand_budget = pop * spend_per_capita * war_volume * recovery_factor * affordability
            demand_budget *= float(settings["economy_scale"])
            demand_budget *= _stable_rand(week, "TOTAL_DEMAND", rand_min, rand_max)

    # Split budget: survival basics first (grain + water), then everything else.
    # Survival supply can be depressed by war, improved by recovery.
    survival_supply = _clamp(0.35 + 0.45 * recovery_factor - 0.25 * war, 0.10, 1.15)

    # Identify survival goods (by name)
    def is_water(n: str) -> bool:
        x = n.lower()
        return x in {"moonwell water", "moonwell water (t1)", "water"}

    def is_grain(n: str) -> bool:
        x = n.lower()
        return x in {"lunar grain", "lunar grain (t1)", "grain"}

    grain_price = next((it["effective_price"] for it in items if is_grain(it["name"])), 1.0)
    water_price = next((it["effective_price"] for it in items if is_water(it["name"])), 1.0)

    grain_qty = _stochastic_int(grain_needed * survival_supply, week, "GRAIN_QTY")
    water_qty = _stochastic_int(water_needed * survival_supply, week, "WATER_QTY")

    survival_spend = float(grain_qty) * float(grain_price) + float(water_qty) * float(water_price)
    remaining_budget = max(0.0, float(demand_budget) - survival_spend)

    # Build weights excluding survival goods (they are already allocated)
    weighted = [it for it in items if not (is_grain(it["name"]) or is_water(it["name"]))]
    total_weight = sum(float(it["weight"]) for it in weighted)
    if total_weight <= 0:
        total_weight = 1.0

    per_item: List[Dict[str, Any]] = []

    gross_value = 0.0
    grain_produced = grain_qty
    water_produced = water_qty

    # Add survival rows to per_item output if they exist in the item list
    for it in items:
        if is_grain(it["name"]):
            v = float(grain_qty) * float(it["effective_price"])
            gross_value += v
            per_item.append(
                {
                    "week": week,
                    "item_name": it["name"],
                    "qty": int(grain_qty),
                    "effective_price": float(it["effective_price"]),
                    "gross_value": float(v),
                    "rarity": it["rarity"],
                    "region": it["region"],
                    "family": it["family"],
                }
            )
        elif is_water(it["name"]):
            v = float(water_qty) * float(it["effective_price"])
            gross_value += v
            per_item.append(
                {
                    "week": week,
                    "item_name": it["name"],
                    "qty": int(water_qty),
                    "effective_price": float(it["effective_price"]),
                    "gross_value": float(v),
                    "rarity": it["rarity"],
                    "region": it["region"],
                    "family": it["family"],
                }
            )

    # Allocate demand across the remaining items
    for it in weighted:
        share = float(it["weight"]) / total_weight
        spend_i = remaining_budget * share
        price_i = float(it["effective_price"]) if float(it["effective_price"]) > 0 else 0.0001
        expected_qty = spend_i / price_i

        # Extra rarity dampener based on production rates (rare items exist but sell less in war)
        rarity = it["rarity"]
        prod_rate = float(rates.get(rarity, 0.00008))
        expected_qty *= _clamp(prod_rate / 0.0010, 0.05, 1.0)

        qty = _stochastic_int(expected_qty, week, f"QTY:{it['name']}")

        value = float(qty) * price_i
        gross_value += value

        per_item.append(
            {
                "week": week,
                "item_name": it["name"],
                "qty": int(qty),
                "effective_price": float(price_i),
                "gross_value": float(value),
                "rarity": it["rarity"],
                "region": it["region"],
                "family": it["family"],
            }
        )

    grain_ratio = (grain_produced / grain_needed) if grain_needed else 1.0
    water_ratio = (water_produced / water_needed) if water_needed else 1.0
    survival_ratio = min(grain_ratio, water_ratio)

    tax_rate = float(settings["tax_rate"])
    tax_income = gross_value * tax_rate
    player_share = float(settings["player_share"])
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

    # Summary per week
    try:
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
    except Exception:
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
            }
        ).execute()
def backfill_gathering_item_families(sb, week: int = 1) -> int:
    """Best-effort: fill missing gathering_items.family based on region rules.

    Returns number of rows updated. Does NOT overwrite existing non-empty family.
    """
    items = sb.table("gathering_items").select("name,region,family").execute().data or []
    updates = []
    for it in items:
        name = (it.get("name") or "").strip()
        region = (it.get("region") or "").strip()
        family = (it.get("family") or "").strip()
        if not name or not region or family:
            continue
        fam = _infer_family_from_region(week, name, region)
        if fam:
            updates.append({"name": name, "family": fam})

    if not updates:
        return 0

    chunk = 200
    for i in range(0, len(updates), chunk):
        sb.table("gathering_items").upsert(updates[i:i+chunk], on_conflict="name").execute()

    return len(updates)

