import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.dm import dm_gate
from utils import infrastructure_effects

UNDO_CATEGORY = "infrastructure"

page_config("Silver Council | Shop", "🏛️")
sidebar("🏛 Shop")

sb = get_supabase()
ensure_bootstrap(sb)

week = get_current_week(sb)
tot = compute_totals(sb, week=week)

st.title("🏛️ Silver Council Shop")
st.caption(f"Week {week} · Moonvault: {tot.gold:,.0f} gold")

# Load catalog + owned
catalog = sb.table("infrastructure").select("name,category,cost,tier,description").order("category").order("tier").order("name").execute().data or []
owned = sb.table("infrastructure_owned").select("name").execute().data or []
owned_set = {o["name"] for o in owned if o.get("name")}

if not catalog:
    st.warning("No infrastructure seeded yet.")
    st.stop()

categories = sorted({c.get("category") or "Other" for c in catalog})
pick_cat = st.selectbox("Category", ["All"] + categories)

shown = [c for c in catalog if (pick_cat == "All" or (c.get("category") or "Other") == pick_cat)]

st.divider()
st.subheader("Available infrastructure")

for item in shown:
    name = item.get("name") or ""
    cost = float(item.get("cost") or 0)
    tier = item.get("tier")
    cat = item.get("category") or "Other"
    owned_flag = name in owned_set
    eff = infrastructure_effects.describe_infrastructure_effect(name)

    with st.container(border=True):
        top = st.columns([3, 1])
        with top[0]:
            st.write(f"**{name}**" + (f" (T{tier})" if tier else ""))
            st.caption(cat)
            if item.get("description"):
                st.write(item["description"])
            if eff:
                st.info(eff)
            if owned_flag:
                st.success("Owned")
        with top[1]:
            st.write(f"Cost: **{cost:,.0f}**")
            if st.button("Buy", key=f"buy_{name}", disabled=owned_flag or tot.gold < cost):
                sb.table("infrastructure_owned").insert({"name": name, "week": week}).execute()
                add_ledger_entry(sb, week=week, direction="out", amount=cost, category="infrastructure_purchase", note=f"Bought {name}")
                st.success("Purchased.")
                st.rerun()

st.divider()
st.subheader("Owned (summary)")
prod_mult = infrastructure_effects.production_multiplier_owned(sb)
social_pts = infrastructure_effects.social_points_owned(sb)
c1, c2 = st.columns(2)
c1.metric("Production multiplier", f"x{prod_mult:.2f}")
c2.metric("Social points", f"{social_pts:d}")
