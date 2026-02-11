import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week

page_config("Economy", "📈")
sidebar("📈 Economy")

sb = get_supabase()
ensure_bootstrap(sb)

week = get_current_week(sb)

st.title("📈 Economy")
st.caption(f"Week {week}")

# Show latest computed economy outputs (usually week-1)
try:
    latest = sb.table("economy_week_output").select("week").order("week", desc=True).limit(1).execute().data
    computed_week = int(latest[0]["week"]) if latest else max(1, week - 1)
except Exception:
    computed_week = max(1, week - 1)

st.caption(f"Latest computed week: {computed_week}")

items = sb.table("gathering_items").select("name,tier,rarity,region,family,base_price_gp,vendor_price_gp,sale_price_gp").execute().data or []
out = sb.table("economy_week_output").select("item_name,effective_price,qty,gross_value,region,family").eq("week", computed_week).execute().data or []
out_map = {r["item_name"]: r for r in out}

rows = []
for it in items:
    name = it.get("name")
    if not name:
        continue
    base = it.get("base_price_gp") or it.get("vendor_price_gp") or it.get("sale_price_gp") or 0
    o = out_map.get(name, {})
    rows.append(
        {
            "Item": name,
            "Tier": it.get("tier"),
            "Rarity": it.get("rarity"),
            "Region": it.get("region") or o.get("region") or "",
            "Family": it.get("family") or o.get("family") or "",
            "Baseline price (gp)": float(base or 0),
            "Current price (gp)": float(o.get("effective_price") or 0),
            "Weekly qty": int(o.get("qty") or 0),
        }
    )

df = pd.DataFrame(rows)
if df.empty:
    st.info("No items found.")
else:
    st.dataframe(df, use_container_width=True, hide_index=True)
