import streamlit as st

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals

page_config("Silver Council | Dashboard", "🏛️")
sidebar("🏛 Dashboard")

sb = get_supabase()
ensure_bootstrap(sb)
current_week = get_current_week(sb)

st.title("🏛️ The Silver Council")
st.caption(f"Dashboard · Current week: {current_week}")

def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def _safe_float(x, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

eco_latest = (
    sb.table("economy_week_summary")
    .select("week,population,survival_ratio,player_payout,tax_income,gross_value,grain_needed,grain_produced,water_needed,water_produced")
    .order("week", desc=True)
    .limit(1)
    .execute()
    .data
    or []
)

eco_week = _safe_int(eco_latest[0]["week"], max(1, current_week - 1)) if eco_latest else max(1, current_week - 1)

tot_now = compute_totals(sb, week=current_week)
tot_eco = compute_totals(sb, week=eco_week)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Moonvault (Gold)", f"{tot_now.gold:,.0f}")
with c2:
    st.metric("Gold gained (latest week)", f"{tot_eco.income:,.0f}")
with c3:
    st.metric("Expenses (latest week)", f"{tot_eco.expenses:,.0f}")
with c4:
    st.metric("Net (latest week)", f"{tot_eco.net:,.0f}")

st.divider()

def _get_pop(w: int):
    try:
        r = sb.table("population_state").select("population").eq("week", w).limit(1).execute().data or []
        if r:
            return _safe_int(r[0].get("population"))
    except Exception:
        pass
    return None

pop_now = _get_pop(current_week)
pop_prev = _get_pop(current_week - 1) if current_week > 1 else None

st.subheader("Population & Survival")

if eco_latest:
    row = eco_latest[0]
    survival = _safe_float(row.get("survival_ratio"), 0.0)
    grain_needed = _safe_float(row.get("grain_needed"), 0.0)
    grain_prod = _safe_int(row.get("grain_produced"), 0)
    water_needed = _safe_float(row.get("water_needed"), 0.0)
    water_prod = _safe_int(row.get("water_produced"), 0)

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        st.metric(
            "Population",
            f"{(pop_now or _safe_int(row.get('population'), 450_000)):,.0f}",
            delta=(None if pop_prev is None or pop_now is None else f"{(pop_now-pop_prev):,}"),
        )
    with cc2:
        st.metric("Survival ratio", f"{survival*100:,.1f}%")
    with cc3:
        st.metric("Latest payout", f"{_safe_float(row.get('player_payout'), 0.0):,.0f} gp")

    st.caption(f"Food: {grain_prod:,.0f} / {grain_needed:,.0f} · Water: {water_prod:,.0f} / {water_needed:,.0f} (Week {eco_week})")
else:
    st.info("No economy computed yet. Advance the week once to generate survival/economy data.")
