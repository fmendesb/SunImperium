import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils import economy

page_config("Economy", "📊")
sidebar("📊 Economy")

sb = get_supabase()
ensure_bootstrap(sb)

current_week = get_current_week(sb)
# Last computed week is usually current_week - 1
computed_week = max(1, current_week - 1)

st.title("📊 Economy")
st.caption(f"Current week: {current_week} · Showing latest computed economy: Week {computed_week}")

# Backfill missing families into gathering_items (best-effort, non-destructive)
try:
    economy.backfill_gathering_item_families(sb, week=computed_week)
except Exception:
    pass

items = (
    sb.table("gathering_items")
    .select("name,rarity,base_price_gp,vendor_price_gp,sale_price_gp,region,family,tier")
    .order("tier")
    .order("name")
    .execute()
    .data
    or []
)

out_rows = (
    sb.table("economy_week_output")
    .select("item_name,qty,effective_price,gross_value,region,family,rarity")
    .eq("week", computed_week)
    .execute()
    .data
    or []
)
out_by_name = {r["item_name"]: r for r in out_rows if r.get("item_name")}

def pick_base_price(it: dict) -> float:
    price = (
        it.get("base_price_gp")
        or it.get("vendor_price_gp")
        or it.get("sale_price_gp")
        or 0
    )
    try:
        return float(price or 0)
    except Exception:
        return 0.0

rows = []
for it in items:
    name = (it.get("name") or "").strip()
    if not name:
        continue
    base_price = pick_base_price(it)
    out = out_by_name.get(name)
    cur_price = float(out.get("effective_price")) if out and out.get("effective_price") is not None else base_price
    qty = int(out.get("qty") or 0) if out else 0
    region = (out.get("region") if out else it.get("region")) or ""
    family = (out.get("family") if out else it.get("family")) or ""
    rows.append(
        {
            "Item": name,
            "Tier": it.get("tier"),
            "Rarity": (out.get("rarity") if out else it.get("rarity")) or "",
            "Region": region,
            "Family": family,
            "Baseline price (gp)": base_price,
            "Current price (gp)": float(cur_price),
            "Weekly qty": qty,
        }
    )

df = pd.DataFrame(rows)
if df.empty:
    st.info("No gathering items found.")
else:
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        q = st.text_input("Search", "")
    with c2:
        reg = st.selectbox("Region", ["All"] + sorted([r for r in df["Region"].dropna().unique().tolist() if r]))
    with c3:
        fam = st.selectbox("Family", ["All"] + sorted([f for f in df["Family"].dropna().unique().tolist() if f]))

    view = df.copy()
    if q:
        view = view[view["Item"].str.contains(q, case=False, na=False)]
    if reg != "All":
        view = view[view["Region"] == reg]
    if fam != "All":
        view = view[view["Family"] == fam]

    st.dataframe(view, use_container_width=True, hide_index=True)
    st.caption("Baseline price comes from gathering_items. Current price/qty come from the latest computed economy_week_output.")
