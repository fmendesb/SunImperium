import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.undo import log_action, get_last_action, pop_last_action


def render():
    UNDO_CATEGORY = "dawnbreakers"


    sb = get_supabase()
    ensure_bootstrap(sb)
    week = get_current_week(sb)

    tot = compute_totals(sb, week=week)

    st.title("🕯️ The Dawnbreakers")
    st.caption(f"Intelligence & Covert Ops · Week {week} · Moonvault: {tot.gold:,.0f} gold")

    with st.popover("↩️ Undo (Dawnbreakers)"):
        last = get_last_action(sb, category=UNDO_CATEGORY)
        if not last:
            st.write("No actions to undo.")
        else:
            payload = last.get("payload") or {}
            st.write(f"Last: {last.get('action','')} · {payload.get('name','')}")
            if st.button("Undo last", key="undo_dawnbreakers"):
                if last.get("action") == "hire_unit":
                    unit_id = payload.get("unit_id")
                    qty = int(payload.get("qty") or 0)
                    cost = float(payload.get("cost") or 0)
                    if unit_id and qty:
                        # reduce roster
                        roster = sb.table("dawnbreakers_roster").select("id,quantity").eq("unit_id", unit_id).limit(1).execute().data
                        if roster:
                            rid = roster[0]["id"]
                            new_q = max(0, int(roster[0]["quantity"]) - qty)
                            sb.table("dawnbreakers_roster").update({"quantity": new_q}).eq("id", rid).execute()
                    if cost:
                        add_ledger_entry(sb, week=week, direction="in", amount=cost, category="undo_refund", note=f"Undo hire: {payload.get('name','unit')}")
                    pop_last_action(sb, action_id=last["id"])
                    st.success("Undone.")
                    st.rerun()
                else:
                    st.error("Undo not implemented for this action type yet.")

    st.divider()

    units = sb.table("dawnbreakers_units").select("id,name,tier,purchase_cost,upkeep,success,description").order("tier").order("name").execute().data
    roster = sb.table("dawnbreakers_roster").select("unit_id,quantity").execute().data
    roster_map = {r["unit_id"]: int(r["quantity"]) for r in roster}

    if not units:
        st.warning("No Dawnbreakers units seeded yet. Seed `dawnbreakers_units` (from Excel).")

    for u in units:
        owned = roster_map.get(u["id"], 0)
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.subheader(u["name"])
                st.write(u.get("description") or "")
                st.write(f"Tier {u.get('tier',1)} · Success {u.get('success',0)}%")
                st.write(f"Cost: {float(u.get('purchase_cost') or 0):,.0f} · Upkeep: {float(u.get('upkeep') or 0):,.0f}")
                st.caption(f"Owned: {owned}")
            with right:
                qty = st.number_input("Qty", min_value=1, max_value=50, value=1, step=1, key=f"qty_{u['id']}")
                total_cost = float(u.get("purchase_cost") or 0) * int(qty)
                can = tot.gold >= total_cost
                if st.button("Hire", key=f"hire_{u['id']}", disabled=not can):
                    sb.table("dawnbreakers_roster").upsert({"unit_id": u["id"], "quantity": owned + int(qty)}).execute()
                    add_ledger_entry(sb, week=week, direction="out", amount=total_cost, category="dawnbreakers_purchase", note=f"Hired {qty}x {u['name']}")
                    log_action(sb, category=UNDO_CATEGORY, action="hire_unit", payload={"unit_id": u["id"], "qty": int(qty), "cost": total_cost, "name": u["name"]})
                    st.success("Hired.")
                    st.rerun()

    st.info("Missions and equipment will be added after the Moonblade squads + war simulator loop is in place.")
