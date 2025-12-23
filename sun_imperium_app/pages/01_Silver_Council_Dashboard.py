import streamlit as st
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals

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
