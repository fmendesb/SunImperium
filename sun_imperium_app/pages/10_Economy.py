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
st.caption("Item prices, weekly volume, and what influences them. Use this to decide which reputations/regions to fix.")


def _infer_family(region: str) -> str:
    r = (region or "").lower().replace("’", "'")
    if "val'har" in r or "valhar" in r:
        return "valar family"
    if "val'heim" in r or "valheim" in r:
        return "valeim family"
    if "ahm'neshti" in r or "ahmneshti" in r or "neshti" in r:
        return "neshti family"
    if "ahel'man" in r or "ahelman" in r:
        return "moonshadow"
    if "new triport" in r or "triport" in r:
        return "lathien"
    if "moonglade" in r:
        return "moonglade families"
    return ""


items = (
    sb.table("gathering_items")
    .select("name,profession,tier,rarity,base_price_gp,vendor_price_gp,sale_price_gp,region,family")
    .execute()
    .data
    or []
)

week_rows = (
    sb.table("economy_week_output")
    .select("item_name,qty,effective_price,gross_value,region,family,rarity")
    .eq("week", week)
    .execute()
    .data
    or []
)

by_name = {r.get("item_name"): r for r in week_rows}

rows = []
for it in items:
    name = it.get("name")
    if not name:
        continue

    region = (it.get("region") or "").strip()
    family = (it.get("family") or "").strip()
    if not family and region:
        family = _infer_family(region)

    # Baseline price (what the item "is"); current price comes from week output
    base_price = (
        it.get("base_price_gp")
        or it.get("vendor_price_gp")
        or it.get("sale_price_gp")
        or 0
    )

    wr = by_name.get(name, {})
    cur_price = float(wr.get("effective_price") or 0)
    qty = int(wr.get("qty") or 0)

    rows.append(
        {
            "Name": name,
            "Profession": it.get("profession") or "—",
            "Tier": it.get("tier") or "—",
            "Rarity": it.get("rarity") or "Common",
            "Region": region or "—",
            "Family": family or "—",
            "Baseline price (gp)": float(base_price or 0),
            "Current price (gp)": cur_price,
            "Weekly qty": qty,
        }
    )

df = pd.DataFrame(rows)

if df.empty:
    st.info("No items found.")
else:
    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        q = st.text_input("Search", placeholder="grain, ore, pearl…")
    with c2:
        tier = st.selectbox("Tier", ["All"] + sorted([t for t in df["Tier"].unique() if str(t) != "nan"], key=str))
    with c3:
        prof = st.selectbox("Profession", ["All"] + sorted(df["Profession"].unique()))

    view = df.copy()
    if q:
        view = view[view["Name"].str.contains(q, case=False, na=False)]
    if tier != "All":
        view = view[view["Tier"] == tier]
    if prof != "All":
        view = view[view["Profession"] == prof]

    st.dataframe(
        view.sort_values(["Profession", "Tier", "Name"], ascending=[True, True, True]),
        use_container_width=True,
        hide_index=True,
    )

st.divider()
st.caption(
    "Current price & weekly qty appear after the DM advances the week (DM Console → Advance Week). "
    "Region/family multipliers come from reputation and region state; war and social infrastructure also influence the result."
)
