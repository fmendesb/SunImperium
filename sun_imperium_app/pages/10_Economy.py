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
current_week = get_current_week(sb)

st.title("📊 Economy")
st.caption("Prices, quantities, and who controls what")

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

# When you Advance Week, the economy is computed for the *closing* week, then current_week increments.
# So the newest computed week is usually (current_week - 1).
def _latest_computed_week() -> int:
    try:
        r = (
            sb.table("economy_week_summary")
            .select("week")
            .order("week", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if r:
            return _safe_int(r[0].get("week"), max(1, current_week - 1))
    except Exception:
        pass
    return max(1, current_week - 1)

latest = _latest_computed_week()
max_week = max(current_week, latest)

week = st.selectbox("Week to view", options=list(range(1, max_week + 1)), index=max(0, latest - 1))
st.caption(f"Viewing Week {week} (current week is {current_week})")

items = (
    sb.table("gathering_items")
    .select("name,tier,rarity,base_price_gp,vendor_price_gp,sale_price_gp,region,family")
    .order("tier")
    .order("name")
    .execute()
    .data
    or []
)

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
    base_price = _safe_float(price, 0.0)

    o = by_name.get(name) or {}
    current_price = _safe_float(o.get("effective_price"), 0.0)
    qty = _safe_int(o.get("qty"), 0)

    rows.append(
        {
            "Tier": _safe_int(it.get("tier"), 1),
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

if not out:
    st.info(
        "No economy output rows for this week yet. "
        "If you just advanced the week, switch the selector to the previous week."
    )
