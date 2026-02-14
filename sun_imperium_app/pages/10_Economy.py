import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week

page_config("Economy", "📊")
sidebar("📊 Economy")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("📊 Economy")
st.caption(f"Week {week} · Prices, quantities, and who controls what")

# Load item catalog
items = (
    sb.table("gathering_items")
    .select("name,tier,rarity,base_price_gp,vendor_price_gp,sale_price_gp,region,family")
    .order("tier")
    .order("name")
    .execute()
    .data
    or []
)

# Load latest computed weekly output (if week hasn't been computed yet, table may be empty)
out = (
    sb.table("economy_week_output")
    .select("item_name,qty,effective_price,gross_value,region,family")
    .eq("week", week)
    .execute()
    .data
    or []
)
by_name = {r.get("item_name"): r for r in out if r.get("item_name")}

rows = []
for it in items:
    name = (it.get("name") or "").strip()
    if not name:
        continue

    price = it.get("base_price_gp") or it.get("vendor_price_gp") or it.get("sale_price_gp") or 0
    base_price = float(price or 0)

    o = by_name.get(name) or {}
    current_price = float(o.get("effective_price") or 0)
    qty = int(o.get("qty") or 0)

    rows.append(
        {
            "Tier": int(it.get("tier") or 1),
            "Rarity": (it.get("rarity") or "Common"),
            "Item": name,
            "Baseline price (gp)": base_price,
            "Current price (gp)": current_price,
            "Weekly qty": qty,
            "Region": (o.get("region") or it.get("region") or ""),
            "Family": (o.get("family") or it.get("family") or ""),
        }
    )

df = pd.DataFrame(rows)

# Filters
c1, c2, c3 = st.columns(3)
with c1:
    tier_sel = st.multiselect("Tier", sorted(df["Tier"].unique().tolist()), default=[])
with c2:
    rarity_sel = st.multiselect("Rarity", sorted(df["Rarity"].unique().tolist()), default=[])
with c3:
    q_only = st.checkbox("Only show traded this week", value=False)

f = df
if tier_sel:
    f = f[f["Tier"].isin(tier_sel)]
if rarity_sel:
    f = f[f["Rarity"].isin(rarity_sel)]
if q_only:
    f = f[f["Weekly qty"] > 0]

st.dataframe(f, use_container_width=True, hide_index=True)

st.caption(
    "Tip: Prices and quantities show after the week economy is computed (Advance Week). "
    "If everything is 0, advance once or check that economy_week_output has rows for this week."
)
