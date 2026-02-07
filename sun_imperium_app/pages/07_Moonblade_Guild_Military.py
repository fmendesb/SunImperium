import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.undo import log_action, get_last_action, pop_last_action

UNDO_CATEGORY = "moonblade"

st.set_page_config(page_title="Moonblade Guild | Military", page_icon="⚔️", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)
tot = compute_totals(sb, week=week)

st.title("⚔️ Moonblade Guild")
st.caption(f"Military · Week {week} · Moonvault: {tot.gold:,.0f} gold")

# Undo
with st.popover("↩️ Undo (Moonblade)"):
    last = get_last_action(sb, category=UNDO_CATEGORY)
    if not last:
        st.write("No actions to undo.")
    else:
        payload = last["payload"] or {}
        st.write(f"Last: {last.get('action','')} · {payload.get('name','')}")
        if st.button("Undo last", key="undo_moonblade"):
            # Undo recruit unit: remove quantity + refund
            if last.get("action") == "recruit_unit":
                unit_id = payload.get("unit_id")
                qty = int(payload.get("qty") or 0)
                refund = float(payload.get("cost") or 0)
                if unit_id and qty:
                    # decrement roster
                    roster = sb.table("moonblade_roster").select("quantity").eq("unit_id", unit_id).limit(1).execute().data
                    if roster:
                        new_qty = max(0, int(roster[0]["quantity"]) - qty)
                        sb.table("moonblade_roster").upsert({"unit_id": unit_id, "quantity": new_qty}).execute()
                if refund:
                    add_ledger_entry(sb, week=week, direction="in", amount=refund, category="undo_refund", note="Undo: recruit unit")
                pop_last_action(sb, action_id=last["id"])
                st.success("Undone.")
                st.rerun()
            else:
                st.error("Undo not implemented for this action type yet.")

st.divider()

# Unit catalog + recruit
units = sb.table("moonblade_units").select("id,name,unit_type,power,cost,upkeep,description").order("unit_type").order("name").execute().data
roster_rows = sb.table("moonblade_roster").select("unit_id,quantity").execute().data
roster_map = {r["unit_id"]: int(r["quantity"]) for r in roster_rows}

st.subheader("Recruitment")
if not units:
    st.warning("No Moonblade units seeded yet. Seed `moonblade_units` from Excel.")
else:
    for u in units:
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.write(f"**{u['name']}**")
                st.caption(u.get("description") or "")
                st.write(f"Cost: {float(u['cost']):,.0f} · Upkeep: {float(u.get('upkeep') or 0):,.0f} · Power: {float(u.get('power') or 0):,.0f}")
                st.write(f"Owned: {roster_map.get(u['id'], 0)}")
            with right:
                qty = st.number_input("Qty", min_value=1, max_value=999, value=1, key=f"qty_{u['id']}")
                total_cost = float(u['cost']) * int(qty)
                if st.button("Recruit", key=f"recruit_{u['id']}", disabled=tot.gold < total_cost):
                    new_qty = roster_map.get(u['id'], 0) + int(qty)
                    sb.table("moonblade_roster").upsert({"unit_id": u['id'], "quantity": new_qty}).execute()
                    add_ledger_entry(sb, week=week, direction="out", amount=total_cost, category="moonblade_recruit", note=f"Recruited {qty}x {u['name']}", metadata={"unit_id": u['id'], "qty": int(qty)})
                    log_action(sb, category=UNDO_CATEGORY, action="recruit_unit", payload={"unit_id": u['id'], "qty": int(qty), "cost": total_cost, "name": u['name']})
                    st.success("Recruited.")
                    st.rerun()

st.divider()

# Squads
st.subheader("Squads")
squads = sb.table("squads").select("id,name,region").order("name").execute().data

with st.form("create_squad", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        squad_name = st.text_input("New squad name")
    with c2:
        region = st.text_input("Region (e.g., New Triport)")
    if st.form_submit_button("Create squad"):
        if squad_name:
            sb.table("squads").insert({"name": squad_name, "region": region}).execute()
            st.success("Squad created.")
            st.rerun()

if not squads:
    st.info("No squads yet. Create one above.")
else:
    squad_options = {s['name']: s for s in squads}
    label = st.selectbox("Select squad", list(squad_options.keys()))
    squad = squad_options[label]

    st.write(f"**{squad['name']}** · Region: {squad.get('region') or '—'}")

    # Squad members
    members = sb.table("squad_members").select("id,unit_id,quantity").eq("squad_id", squad["id"]).execute().data
    unit_by_id = {u["id"]: u for u in units}

    mrows = []
    for m in members:
        u = unit_by_id.get(m["unit_id"])
        if not u:
            continue
        mrows.append({"Member ID": m["id"], "Unit": u["name"], "Qty": int(m["quantity"])})
    if mrows:
        st.dataframe(pd.DataFrame(mrows), use_container_width=True)
    else:
        st.caption("No members assigned yet.")

    st.markdown("#### Assign units")
    # only units you own
    owned_units = [u for u in units if roster_map.get(u["id"], 0) > 0]
    if not owned_units:
        st.info("Recruit units first.")
    else:
        pick = st.selectbox("Unit", [f"{u['name']} ({u['unit_type']})" for u in owned_units])
        chosen = owned_units[[f"{u['name']} ({u['unit_type']})" for u in owned_units].index(pick)]
        max_add = roster_map.get(chosen["id"], 0)
        qty_add = st.number_input("Add qty", min_value=1, max_value=max_add, value=1)
        if st.button("Add to squad"):
            # decrement roster, increment squad member
            sb.table("moonblade_roster").upsert({"unit_id": chosen["id"], "quantity": max_add - int(qty_add)}).execute()
            # upsert member by (squad_id, unit_id)
            # Supabase doesn't have composite unique in this quick schema; we'll emulate by fetch/update.
            existing = (
                sb.table("squad_members")
                .select("id,quantity")
                .eq("squad_id", squad["id"])
                .eq("unit_id", chosen["id"])
                .limit(1)
                .execute()
                .data
            )
            if existing:
                sb.table("squad_members").update({"quantity": int(existing[0]["quantity"]) + int(qty_add)}).eq("id", existing[0]["id"]).execute()
            else:
                sb.table("squad_members").insert({"squad_id": squad["id"], "unit_id": chosen["id"], "quantity": int(qty_add)}).execute()

            st.success("Assigned.")
            st.rerun()

st.info("War Simulator is available on its own page. You select the friendly squad; the DM inputs the enemy force.")
