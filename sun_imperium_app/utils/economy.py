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


def get_settings(sb) -> Dict[str, float]:
    """Read economy settings. Must exist via SQL seed."""
    r = sb.table("economy_settings").select("tax_rate,player_share,economy_scale,rand_min,rand_max").limit(1).execute()
    if not r.data:
        return {"tax_rate": 0.10, "player_share": 0.20, "economy_scale": 1.0, "rand_min": 0.90, "rand_max": 1.10}
    row = r.data[0]
    return {
        "tax_rate": float(row.get("tax_rate") or 0.10),
        "player_share": float(row.get("player_share") or 0.20),
        "economy_scale": float(row.get("economy_scale") or 1.0),
        "rand_min": float(row.get("rand_min") or 0.90),
        "rand_max": float(row.get("rand_max") or 1.10),
    }


def rarity_rates(sb) -> Dict[str, float]:
    r = sb.table("rarity_prod_rates").select("rarity,prod_rate").execute()
    rates: Dict[str, float] = {}
    for row in (r.data or []):
        rates[(row.get("rarity") or "").strip()] = float(row.get("prod_rate") or 0)
    return rates


def get_population(sb, week: int) -> int:
    r = sb.table("population_state").select("population").eq("week", week).limit(1).execute()
    if r.data:
        return int(r.data[0]["population"])
    return 450_000


def _stable_rand(week: int, key: str, a: float, b: float) -> float:
    h = hashlib.sha256(f"{week}:{key}".encode("utf-8")).hexdigest()
    seed = int(h[:8], 16)
    rng = random.Random(seed)
    return rng.uniform(a, b)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _infer_family_from_region(week: int, item_name: str, region: str) -> str:
    r = (region or "").lower()
    # Normalize apostrophes variants
    r = r.replace("’", "'")

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
        # deterministic pick so it doesn't reshuffle every rerun
        choices = ["eladrin", "elenwe", "galadhel"]
        h = hashlib.sha256(f"{week}:{item_name}:{region}".encode("utf-8")).hexdigest()
        return choices[int(h[:2], 16) % len(choices)]
    return ""


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


def compute_week_economy(sb, week: int) -> Tuple[WeekEconomyResult, List[Dict[str, Any]]]:
    """Compute weekly production, values, and taxes.

    Returns (summary, per_item_rows)
    """
    settings = get_settings(sb)
    rates = rarity_rates(sb)

    pop = get_population(sb, week)
    grain_needed = pop * GRAIN_PER_CAPITA
    water_needed = pop * WATER_PER_CAPITA

    rand_min, rand_max = settings["rand_min"], settings["rand_max"]
    scale = settings["economy_scale"]

    items = (
        sb.table("gathering_items")
        .select("name,rarity,base_price_gp,region,family")
        .execute()
        .data
        or []
    )

    per_item: List[Dict[str, Any]] = []
    gross_value = 0.0
    grain_produced = 0
    water_produced = 0

    for it in items:
        name = it["name"]
        rarity = (it.get("rarity") or "").strip()
        base_price = float(it.get("base_price_gp") or 0)
        region = (it.get("region") or "").strip()
        family = (it.get("family") or "").strip()

        # Backfill missing family (important for reputation -> economy linkage)
        if not family and region:
            family = _infer_family_from_region(week, name, region)

        if name.lower() in {"moonwell water", "moonwell water (t1)", "water"}:
            prod_rate = WATER_PER_CAPITA
        elif name.lower() in {"lunar grain", "lunar grain (t1)", "grain"}:
            prod_rate = GRAIN_PER_CAPITA
        else:
            prod_rate = float(rates.get(rarity, 0.00008))

        rm = region_multiplier(sb, week, region) if region else 1.0
        fm = family_multiplier(sb, week, family) if family else 1.0
        rf = _stable_rand(week, name, rand_min, rand_max)

        qty = int(round(pop * prod_rate * scale * rm * fm * rf))
        if qty < 0:
            qty = 0

        effective_price = base_price * rm * fm
        value = qty * effective_price

        gross_value += value
        if name.lower().startswith("moonwell water") or name.lower() == "water":
            water_produced += qty
        if name.lower().startswith("lunar grain") or name.lower() == "grain":
            grain_produced += qty

        per_item.append(
            {
                "week": week,
                "item_name": name,
                "qty": qty,
                "effective_price": float(effective_price),
                "gross_value": float(value),
                "rarity": rarity,
                "region": region,
                "family": family,
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
        }
    ).execute()
