import streamlit as st
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals
from utils import economy



st.set_page_config(page_title="Silver Council | Dashboard", page_icon="🏛️", layout="wide")

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
    "population,survival_ratio,player_payout,tax_income,gross_value"
).eq("week", week).limit(1).execute().data

if eco:
    row = eco[0]
    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.metric("Population", f"{int(row.get('population') or 0):,}")
    with e2:
        st.metric("Survival ratio", f"{float(row.get('survival_ratio') or 0):.2f}")
    with e3:
        st.metric("Tax income (total)", f"{float(row.get('tax_income') or 0):,.0f}")
    with e4:
        st.metric("Player payout", f"{float(row.get('player_payout') or 0):,.0f}")
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
