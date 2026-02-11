import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals
from utils import economy
from utils import infrastructure_effects

page_config("Sun Imperium | Silver Council Dashboard", "🏛️")
sidebar("🏛 Dashboard")

sb = get_supabase()
ensure_bootstrap(sb)

current_week = get_current_week(sb)

# We show the latest week that has an economy summary (usually current_week-1 right after advancing).
try:
    latest = sb.table("economy_week_summary").select("week").order("week", desc=True).limit(1).execute().data
    computed_week = int(latest[0]["week"]) if latest else max(1, current_week - 1)
except Exception:
    computed_week = max(1, current_week - 1)

tot = compute_totals(sb, week=computed_week)

st.title("🏛️ The Silver Council")
st.caption(f"Dashboard · Current week: {current_week} · Latest computed week: {computed_week}")

# --- Helpers ---
def _sum_player_payout(week: int) -> float:
    try:
        rows = (
            sb.table("ledger_entries")
            .select("amount")
            .eq("week", week)
            .eq("category", "player_payout")
            .execute()
            .data
            or []
        )
        return float(sum(float(r.get("amount") or 0) for r in rows))
    except Exception:
        return 0.0

def _population(week: int) -> int | None:
    try:
        r = sb.table("population_state").select("population").eq("week", week).limit(1).execute().data
        if r:
            return int(r[0]["population"])
    except Exception:
        pass
    return None

def _survival_ratio(week: int) -> float | None:
    try:
        r = sb.table("economy_week_summary").select("survival_ratio").eq("week", week).limit(1).execute().data
        if r and r[0].get("survival_ratio") is not None:
            return float(r[0]["survival_ratio"])
    except Exception:
        pass
    return None

def _war_severity() -> float:
    try:
        s = economy.get_settings(sb)
        return float(s.get("war_severity") or 0.0)
    except Exception:
        return 0.0

def _friendly_squads_overview() -> pd.DataFrame:
    # best-effort: works with current squads schema (squads + squad_members + moonblade_units)
    try:
        squads = sb.table("squads").select("id,name,region").order("name").execute().data or []
    except Exception:
        squads = []
    if not squads:
        return pd.DataFrame()

    try:
        units = sb.table("moonblade_units").select("id,name,unit_type,power").execute().data or []
        unit_power = {u["id"]: float(u.get("power") or 0) for u in units}
    except Exception:
        unit_power = {}

    rows = []
    for s in squads:
        sid = s["id"]
        try:
            members = sb.table("squad_members").select("unit_id,quantity,unit_type").eq("squad_id", sid).execute().data or []
        except Exception:
            members = []
        total_power = 0.0
        total_units = 0
        for m in members:
            qty = int(m.get("quantity") or 0)
            total_units += qty
            total_power += qty * float(unit_power.get(m.get("unit_id"), 0))
        rows.append(
            {
                "Squad": s.get("name"),
                "Region": s.get("region") or "—",
                "Units": total_units,
                "Power": round(total_power, 2),
            }
        )
    return pd.DataFrame(rows)

# --- Core values ---
moonvault_gold = float(getattr(tot, "gold", 0.0) or 0.0)
payout = _sum_player_payout(computed_week)

pop_now = _population(computed_week) or 450_000
pop_prev = _population(computed_week - 1)
pop_delta = (pop_now - pop_prev) if pop_prev is not None else None

survival = _survival_ratio(computed_week)
war = _war_severity()
war_label = "WAR" if war >= 0.5 else "Peace"

baseline_payout = 0.0
try:
    baseline_payout = economy.estimate_baseline_player_payout(sb, computed_week, population=pop_now)
except Exception:
    baseline_payout = 0.0

econ_pct = (payout / baseline_payout * 100.0) if baseline_payout > 0 else None

# --- UI ---
c1, c2, c3, c4 = st.columns(4)
c1.metric("Moonvault (Gold)", f"{moonvault_gold:,.0f}")
c2.metric("Player payout (this week)", f"{payout:,.0f}")
c3.metric("Expenses (this week)", f"{float(getattr(tot, 'expenses', 0.0) or 0.0):,.0f}")
c4.metric("Economy vs baseline", ("—" if econ_pct is None else f"{econ_pct:.0f}%"))

st.divider()

st.subheader("Population & Survival")
p1, p2, p3 = st.columns(3)
p1.metric("Population", f"{pop_now:,.0f}", (None if pop_delta is None else f"{pop_delta:+,d}"))
p2.metric("Survival ratio", ("—" if survival is None else f"{survival:.2f}"))
p3.metric("War status", war_label)

st.caption("Population updates after week advancement. War status is driven by Economy Settings (DM-controlled).")

st.divider()

st.subheader("Forces in the field")
df_squads = _friendly_squads_overview()
if df_squads.empty:
    st.info("No squads created yet.")
else:
    st.dataframe(df_squads, use_container_width=True, hide_index=True)

st.divider()

st.subheader("Infrastructure impact (owned)")
prod_mult = infrastructure_effects.production_multiplier_owned(sb)
social_pts = infrastructure_effects.social_points_owned(sb)
i1, i2 = st.columns(2)
i1.metric("Production multiplier", f"x{prod_mult:.2f}")
i2.metric("Social points", f"{social_pts:d}")

st.caption("Infrastructure bonuses feed into recovery and demand (economy).")
