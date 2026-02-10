import streamlit as st

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals
from utils import infrastructure_effects


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

# Economy snapshot (from last computed week)
eco = sb.table("economy_week_summary").select(
    "population,survival_ratio,player_payout,tax_income,gross_value,grain_needed,grain_produced,water_needed,water_produced"
).eq("week", week).limit(1).execute().data

if eco:
    row = eco[0]
    e1, e2, e3, e4 = st.columns(4)
    # Population trend (from population_state if present)
    pop_now = int(row.get("population") or 0)
    pop_prev = None
    try:
        prev = (
            sb.table("population_state")
            .select("population")
            .eq("week", max(1, week - 1))
            .limit(1)
            .execute()
            .data
        )
        if prev:
            pop_prev = int(prev[0].get("population") or 0)
    except Exception:
        pop_prev = None

    # Satisfaction is a lightweight proxy: social infrastructure + survival.
    social_bonus = infrastructure_effects.social_bonus_total(sb)
    surv = float(row.get("survival_ratio") or 0)
    # Simple mapping into a readable 0..100 band.
    satisfaction = max(0.0, min(100.0, 50.0 + social_bonus * 8.0 + (surv - 1.0) * 40.0))

    with e1:
        delta = None if pop_prev is None else pop_now - pop_prev
        st.metric("Population", f"{pop_now:,}", delta=None if delta is None else f"{delta:+,}")
    with e2:
        st.metric("Survival ratio", f"{float(row.get('survival_ratio') or 0):.2f}")
    with e3:
        st.metric("Tax income (total)", f"{float(row.get('tax_income') or 0):,.0f}")
    with e4:
        st.metric("Player payout", f"{float(row.get('player_payout') or 0):,.0f}")

    g1, g2 = st.columns(2)
    with g1:
        st.write(
            f"**Grain:** {int(row.get('grain_produced') or 0):,} / {float(row.get('grain_needed') or 0):,.0f} needed"
        )
    with g2:
        st.write(
            f"**Water:** {int(row.get('water_produced') or 0):,} / {float(row.get('water_needed') or 0):,.0f} needed"
        )

    st.divider()
    s1, s2, s3 = st.columns(3)
    with s1:
        st.metric("Satisfaction", f"{satisfaction:,.0f}/100")
    with s2:
        st.metric("Social infrastructure", f"+{social_bonus:.0f}")
    with s3:
        prod_mult = infrastructure_effects.production_multiplier_total(sb)
        st.metric("Production multiplier", f"x{prod_mult:.2f}")
else:
    st.warning("Economy not computed for this week yet. Use DM Console → Advance Week to generate income.")

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
