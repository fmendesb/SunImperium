import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.undo import log_action, get_last_action, pop_last_action


def render():
    UNDO_CATEGORY = "diplomacy"


    sb = get_supabase()
    ensure_bootstrap(sb)
    week = get_current_week(sb)

    st.title("🤝 Silver Council: Diplomacy")
    tot = compute_totals(sb, week=week)
    st.caption(f"Week {week} · Moonvault: {tot.gold:,.0f} gold")

    # Undo
    with st.popover("↩️ Undo (Diplomacy)"):
        last = get_last_action(sb, category=UNDO_CATEGORY)
        if not last:
            st.write("No actions to undo.")
        else:
            payload = last["payload"] or {}
            st.write(f"Last: {last.get('action','')} · {payload.get('unit_name','')}")
            if st.button("Undo last", key="undo_dipl"):
                if last["action"] == "recruit_diplomacy_unit":
                    roster_id = payload.get("roster_id")
                    cost = float(payload.get("cost") or 0)
                    if roster_id:
                        sb.table("diplomacy_roster").delete().eq("id", roster_id).execute()
                    if cost:
                        add_ledger_entry(sb, week=week, direction="in", amount=cost, category="undo_refund", note="Undo diplomacy recruit")
                    pop_last_action(sb, action_id=last["id"])
                    st.success("Undone.")
                    st.rerun()
                else:
                    st.error("Undo not implemented for this action.")

    units = sb.table("diplomacy_units").select("id,name,tier,purchase_cost,upkeep,description").order("tier").order("name").execute().data
    roster = sb.table("diplomacy_roster").select("id,unit_id,quantity").execute().data
    roster_map = {r["unit_id"]: r for r in roster}

    if not units:
        st.warning("No diplomacy units seeded yet. Seed `diplomacy_units` (from Excel or manually).")
    else:
        st.subheader("Recruit Envoys & Ambassadors")
        for u in units:
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    st.write(f"**{u['name']}** (Tier {u['tier']})")
                    if u.get("description"):
                        st.write(u["description"])
                    st.caption(f"Cost: {float(u['purchase_cost']):,.0f} · Upkeep: {float(u.get('upkeep') or 0):,.0f}")
                with right:
                    owned_qty = int(roster_map.get(u["id"], {}).get("quantity", 0))
                    st.write(f"Owned: **{owned_qty}**")
                    can_buy = tot.gold >= float(u["purchase_cost"])
                    if st.button("Recruit", key=f"recruit_{u['id']}", disabled=not can_buy):
                        row = roster_map.get(u["id"])
                        if row:
                            sb.table("diplomacy_roster").update({"quantity": owned_qty + 1}).eq("id", row["id"]).execute()
                            roster_id = row["id"]
                        else:
                            ins = sb.table("diplomacy_roster").insert({"unit_id": u["id"], "quantity": 1}).execute()
                            roster_id = ins.data[0]["id"] if ins.data else None
                        add_ledger_entry(sb, week=week, direction="out", amount=float(u["purchase_cost"]), category="diplomacy_purchase", note=f"Recruited {u['name']}", metadata={"unit_id": u["id"]})
                        log_action(sb, category=UNDO_CATEGORY, action="recruit_diplomacy_unit", payload={"roster_id": roster_id, "unit_id": u["id"], "unit_name": u["name"], "cost": float(u["purchase_cost"])})
                        st.success("Recruited.")
                        st.rerun()

    st.info("Upkeep is applied during the weekly tick (Advance Week).")
