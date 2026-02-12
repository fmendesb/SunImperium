import streamlit as st

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals


page_config("Silver Council | Dashboard", "🏛️")
sidebar("🏛 Dashboard")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

tot = compute_totals(sb, week=week)

st.title("🏛️ The Silver Council")
st.caption(f"Dashboard · Week {week}")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Moonvault (Gold)", f"{tot.gold:,.0f}")
with c2:
    st.metric("Income (this week)", f"{tot.income:,.0f}")
with c3:
    st.metric("Expenses (this week)", f"{tot.expenses:,.0f}")
with c4:
    st.metric("Net (this week)", f"{tot.net:,.0f}")

st.divider()

# -------------------------
# Population + Survival (latest computed week)
# -------------------------

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


def _get_population_state(w: int) -> int | None:
    try:
        r = (
            sb.table("population_state")
            .select("population")
            .eq("week", w)
            .limit(1)
            .execute()
            .data
        )
        if r:
            return _safe_int(r[0].get("population"))
    except Exception:
        return None
    return None


pop_now = _get_population_state(week)
pop_prev = _get_population_state(week - 1) if week > 1 else None

# Economy snapshot: show the most recent computed week (<= current)
eco = (
    sb.table("economy_week_summary")
    .select(
        "week,population,survival_ratio,player_payout,tax_income,gross_value,grain_needed,grain_produced,water_needed,water_produced"
    )
    .lte("week", week)
    .order("week", desc=True)
    .limit(1)
    .execute()
    .data
)

if eco:
    row = eco[0]
    eco_week = _safe_int(row.get("week"), week)

    # Prefer population_state (because it includes war casualties + gentle drift), fall back to economy summary.
    pop_display = pop_now if pop_now is not None else _safe_int(row.get("population"), 450_000)
    pop_delta = None
    if pop_prev is not None and pop_display is not None:
        pop_delta = pop_display - pop_prev

    survival = _safe_float(row.get("survival_ratio"), 0.0)
    grain_needed = _safe_float(row.get("grain_needed"), 0.0)
    grain_prod = _safe_int(row.get("grain_produced"), 0)
    water_needed = _safe_float(row.get("water_needed"), 0.0)
    water_prod = _safe_int(row.get("water_produced"), 0)

    st.subheader("Population & Survival")
    if eco_week != week:
        st.caption(f"Latest computed economy: Week {eco_week}")

    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.metric(
            "Population",
            f"{_safe_int(pop_display):,}",
            delta=(f"{pop_delta:+,}" if pop_delta is not None else None),
        )
    with e2:
        st.metric("Survival ratio", f"{survival:.2f}")
    with e3:
        st.metric("Tax income (total)", f"{_safe_float(row.get('tax_income')):,.0f}")
    with e4:
        st.metric("Player payout", f"{_safe_float(row.get('player_payout')):,.0f}")

    # Food/water detail
    g1, g2 = st.columns(2)
    with g1:
        if grain_needed > 0:
            ratio = min(1.0, grain_prod / grain_needed)
            st.write(f"**Grain:** {grain_prod:,} / {grain_needed:,.0f} needed ({ratio*100:.0f}%)")
            st.progress(ratio)
        else:
            st.write("**Grain:** —")
    with g2:
        if water_needed > 0:
            ratio = min(1.0, water_prod / water_needed)
            st.write(f"**Water:** {water_prod:,} / {water_needed:,.0f} needed ({ratio*100:.0f}%)")
            st.progress(ratio)
        else:
            st.write("**Water:** —")

else:
    st.warning(
        "Economy not computed yet. Use DM Console → Advance Week to generate the first economy summary."
    )

# Upkeep breakdown chips for this week
wk_rows = sb.table("ledger_entries").select("category,direction,amount").eq("week", week).execute().data

def sum_cat(prefix: str) -> float:
    return sum(float(r["amount"]) for r in wk_rows if r["direction"] == "out" and r["category"].startswith(prefix))

u1, u2, u3, u4 = st.columns(4)
with u1:
    st.metric("Moonblade Guild upkeep", f"{sum_cat('moonblade_'):,.0f}")
with u2:
    st.metric("Dawnbreakers upkeep", f"{sum_cat('dawnbreakers_'):,.0f}")
with u3:
    st.metric("Diplomacy upkeep", f"{sum_cat('diplomacy_'):,.0f}")
with u4:
    st.metric("Infrastructure upkeep", f"{sum_cat('infrastructure_'):,.0f}")

st.info("Tip: Infrastructure purchases and recruiting units immediately reduce the Moonvault. Weekly income/upkeep is applied when the week advances.")
