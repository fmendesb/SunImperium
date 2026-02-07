import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.undo import log_action, get_last_action, pop_last_action
from utils.infrastructure_effects import effect_for_infrastructure, prereq_name_for_infrastructure
from utils.navigation import sidebar_nav

UNDO_CATEGORY = "infrastructure"

st.set_page_config(page_title="Silver Council | Shop", page_icon="🏪", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
sidebar_nav(sb)
week = get_current_week(sb)

tot = compute_totals(sb, week=week)

st.title("🏪 Silver Council Shop")
st.caption(f"Shop · Week {week} · Moonvault: {tot.gold:,.0f} gold")

# Undo last infrastructure purchase
with st.popover("↩️ Undo (Infrastructure)"):
    last = get_last_action(sb, category=UNDO_CATEGORY)
    if not last:
        st.write("No actions to undo.")
    else:
        payload = last["payload"] or {}
        action = last.get("action", "")
        name = (payload or {}).get("name", "")
        st.write(f"Last: {action} · {name}")
        if st.button("Undo last", key="undo_infra"):
            # Revert ownership + refund gold
            infra_id = payload.get("infrastructure_id")
            cost = float(payload.get("cost") or 0)
            name = payload.get("name") or "Infrastructure"
            if infra_id:
                sb.table("infrastructure_owned").upsert({"infrastructure_id": infra_id, "owned": False}).execute()
            if cost:
                add_ledger_entry(sb, week=week, direction="in", amount=cost, category="undo_refund", note=f"Undo: {name}")
            pop_last_action(sb, action_id=last["id"])
            st.success("Undone.")
            st.rerun()

st.divider()

# Fetch infra + ownership
infra = sb.table("infrastructure").select("id,name,category,cost,upkeep,description,prereq").order("category").order("name").execute().data
owned_rows = sb.table("infrastructure_owned").select("infrastructure_id,owned").execute().data
owned_map = {r["infrastructure_id"]: bool(r["owned"]) for r in owned_rows}

# Helper: resolve prereq name -> owned status
name_to_id = {row["name"]: row["id"] for row in (infra or [])}


def _owned_by_name(name: str) -> bool:
    pid = name_to_id.get((name or "").strip())
    return bool(pid and owned_map.get(pid, False))


def prereq_met(row: dict) -> bool:
    """Return True if the prerequisite is owned.

    We support:
    - explicit infrastructure.prereq (string name)
    - inferred prereqs based on canonical name chains (from design docs)
    """
    explicit = (row.get("prereq") or "").strip()
    inferred = prereq_name_for_infrastructure(row.get("name") or "")
    prereq_name = explicit or inferred or ""
    if not prereq_name:
        return True
    return _owned_by_name(prereq_name)

if not infra:
    st.warning("No infrastructure seeded yet. Seed `infrastructure` table (from Excel or manually).")
    st.stop()

# Group by category
by_cat: dict[str, list[dict]] = {}
for row in infra:
    by_cat.setdefault(row["category"], []).append(row)

cats = list(by_cat.keys())
selected_cat = st.selectbox("Category", cats, index=0)

rows = []
for row in by_cat[selected_cat]:
    is_owned = owned_map.get(row["id"], False)
    rows.append(
        {
            "id": row["id"],
            "Name": row["name"],
            "Cost": float(row["cost"]),
            "Upkeep": float(row.get("upkeep") or 0),
            "Owned": "Yes" if is_owned else "No",
            "Prereq": row.get("prereq") or "",
            "Description": row.get("description") or "",
        }
    )

df = pd.DataFrame(rows)

for _, r in df.iterrows():
    with st.container(border=True):
        left, right = st.columns([3, 1])
        with left:
            st.subheader(r["Name"])
            st.write(r["Description"])
            st.write(f"**Cost:** {r['Cost']:,.0f} · **Upkeep:** {r['Upkeep']:,.0f}")
            # Benefits (explicit)
            eff = effect_for_infrastructure(r["Name"])
            if eff:
                if eff.unit == "%":
                    st.write(f"**Benefits:** +{eff.value:g}{eff.unit} to {eff.target} success")
                elif eff.unit == "x":
                    st.write(f"**Benefits:** {eff.value:g}{eff.unit} {eff.target}")
                elif eff.kind == "social_bonus":
                    st.write(f"**Benefits:** +{eff.value:g} Social Status")
                elif eff.kind == "power_bonus":
                    st.write(f"**Benefits:** +{eff.value:g} Power Level to {eff.target.title()} units")
            prereq_label = (r["Prereq"] or prereq_name_for_infrastructure(r["Name"]) or "").strip()
            if prereq_label:
                st.caption(f"Prerequisite: {prereq_label}")
        with right:
            owned = r["Owned"] == "Yes"
            st.write(f"**Owned:** {'✅' if owned else '❌'}")
            prereq_ok = prereq_met({"name": r["Name"], "prereq": r["Prereq"]})
            can_buy = (not owned) and prereq_ok and (tot.gold >= float(r["Cost"]))
            if (not prereq_ok) and (r["Prereq"] or prereq_name_for_infrastructure(r["Name"])):
                st.caption("🔒 Locked until prerequisite is owned.")
            if st.button("Purchase", key=f"buy_{r['id']}", disabled=not can_buy):
                # Mark owned + deduct gold via ledger
                sb.table("infrastructure_owned").upsert({"infrastructure_id": r["id"], "owned": True}).execute()
                add_ledger_entry(
                    sb,
                    week=week,
                    direction="out",
                    amount=float(r["Cost"]),
                    category="infrastructure_purchase",
                    note=f"Purchased {r['Name']}",
                    metadata={"infrastructure_id": r["id"]},
                )
                log_action(
                    sb,
                    category=UNDO_CATEGORY,
                    action="purchase_infrastructure",
                    payload={"infrastructure_id": r["id"], "cost": float(r["Cost"]), "name": r["Name"]},
                )
                st.success("Purchased.")
                st.rerun()

st.info("Purchases are instant. Upkeep is applied during the weekly tick (Advance Week).")
