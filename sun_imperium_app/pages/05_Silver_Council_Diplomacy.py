import json
import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.undo import log_action, get_last_action, pop_last_action
from utils.dm import dm_gate
from utils.equipment import (
    get_equipment_items,
    get_equipment_inventory,
    add_equipment,
    compute_equipment_bonus_pct,
)
from utils.missions import list_missions, create_mission, resolve_mission
from utils.activity import log_activity
from utils.infrastructure_effects import success_bonus_pct_for_category
from utils.navigation import sidebar_nav


UNDO_CATEGORY = "diplomacy"

st.set_page_config(page_title="Silver Council | Diplomacy", page_icon="🤝", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
sidebar_nav(sb)
week = get_current_week(sb)

tot = compute_totals(sb, week=week)

st.title("🤝 Silver Council: Diplomacy")
st.caption(f"Week {week} · Moonvault: {tot.gold:,.0f} gold")


# ---------- Data ----------
units = (
    sb.table("diplomacy_units")
    .select("id,name,tier,purchase_cost,upkeep,success,description")
    .order("tier")
    .order("name")
    .execute()
    .data
    or []
)
roster_rows = sb.table("diplomacy_roster").select("id,unit_id,quantity").execute().data or []
roster_map = {r["unit_id"]: r for r in roster_rows}

equip_items = get_equipment_items(sb, "diplomacy")
equip_inv = get_equipment_inventory(sb, "diplomacy")

missions = list_missions(sb, "diplomacy_missions", week)


def missions_qty_by_unit(active_only: bool = True):
    m = {}
    for row in missions:
        if active_only and str(row.get("status")) != "active":
            continue
        uid = row.get("unit_id")
        m[uid] = int(m.get(uid, 0)) + int(row.get("quantity") or 0)
    return m


active_assigned = missions_qty_by_unit(True)


# ---------- Undo ----------
with st.popover("↩️ Undo (Diplomacy)"):
    last = get_last_action(sb, category=UNDO_CATEGORY)
    if not last:
        st.write("No actions to undo.")
    else:
        payload = last["payload"] or {}
        st.write(f"Last: {last.get('action','')} · {payload.get('label','')}")
        if st.button("Undo last", key="undo_dipl"):
            if last.get("action") == "recruit_diplomacy_unit":
                unit_id = payload.get("unit_id")
                cost = float(payload.get("cost") or 0)
                if unit_id:
                    row = roster_map.get(unit_id)
                    if row:
                        q = int(row.get("quantity") or 0)
                        sb.table("diplomacy_roster").update({"quantity": max(0, q - 1)}).eq("id", row["id"]).execute()
                if cost:
                    add_ledger_entry(sb, week=week, direction="in", amount=cost, category="undo_refund", note="Undo diplomacy recruit")
                pop_last_action(sb, action_id=last["id"])
                st.success("Undone.")
                st.rerun()
            elif last.get("action") == "buy_diplomacy_equipment":
                eq_id = payload.get("equipment_id")
                cost = float(payload.get("cost") or 0)
                if eq_id:
                    add_equipment(sb, category="diplomacy", equipment_id=eq_id, delta=-1)
                if cost:
                    add_ledger_entry(sb, week=week, direction="in", amount=cost, category="undo_refund", note="Undo equipment purchase")
                pop_last_action(sb, action_id=last["id"])
                st.success("Undone.")
                st.rerun()
            else:
                st.error("Undo not implemented for this action.")


tab_recruit, tab_equip, tab_missions = st.tabs(["Recruit", "Equipment", "Missions"])


# ---------- Recruit ----------
with tab_recruit:
    st.subheader("Recruit Envoys & Ambassadors")
    st.caption("Success chance is shown per tier; equipment can increase it.")

    if not units:
        st.warning("No diplomacy units seeded yet.")
    else:
        for u in units:
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    base_success = float(u.get("success") or 0)
                    st.write(f"**{u['name']}** (Tier {u['tier']})")
                    if u.get("description"):
                        st.write(u["description"])
                    st.caption(
                        f"Cost: {float(u['purchase_cost']):,.0f} · Upkeep: {float(u.get('upkeep') or 0):,.0f} · Base success: {base_success:.0f}%"
                    )
                with right:
                    owned_qty = int(roster_map.get(u["id"], {}).get("quantity", 0))
                    assigned = int(active_assigned.get(u["id"], 0))
                    available = max(0, owned_qty - assigned)
                    st.write(f"Owned: **{owned_qty}**")
                    st.caption(f"Available (not on missions): {available}")
                    can_buy = tot.gold >= float(u["purchase_cost"])
                    if st.button("Recruit", key=f"recruit_{u['id']}", disabled=not can_buy):
                        row = roster_map.get(u["id"])
                        if row:
                            sb.table("diplomacy_roster").update({"quantity": owned_qty + 1}).eq("id", row["id"]).execute()
                        else:
                            sb.table("diplomacy_roster").insert({"unit_id": u["id"], "quantity": 1}).execute()

                        add_ledger_entry(
                            sb,
                            week=week,
                            direction="out",
                            amount=float(u["purchase_cost"]),
                            category="diplomacy_purchase",
                            note=f"Recruited {u['name']}",
                            metadata={"unit_id": u["id"]},
                        )
                        log_action(
                            sb,
                            category=UNDO_CATEGORY,
                            action="recruit_diplomacy_unit",
                            payload={"unit_id": u["id"], "label": u["name"], "cost": float(u["purchase_cost"])},
                        )
                        log_activity(sb, kind="diplomacy", message=f"Recruited {u['name']}", meta={"unit_id": u["id"], "week": week})
                        st.success("Recruited.")
                        st.rerun()


# ---------- Equipment ----------
with tab_equip:
    st.subheader("Diplomacy Equipment")
    st.caption("Equipment provides flat percentage bonuses to mission success.")

    if not equip_items:
        st.info("No diplomacy equipment seeded yet. Add rows to mission_equipment (category='diplomacy').")
    else:
        for e in equip_items:
            with st.container(border=True):
                left, right = st.columns([3, 1])
                with left:
                    st.write(f"**{e['name']}**")
                    if e.get("description"):
                        st.write(e["description"])
                    st.caption(
                        f"Cost: {float(e.get('cost') or 0):,.0f} · Success bonus: {float(e.get('success_bonus_pct') or 0):.0f}%"
                    )
                with right:
                    owned = int(equip_inv.get(e["id"], 0))
                    st.write(f"Owned: **{owned}**")
                    can_buy = tot.gold >= float(e.get("cost") or 0)
                    if st.button("Buy", key=f"buy_eq_{e['id']}", disabled=not can_buy):
                        add_equipment(sb, category="diplomacy", equipment_id=e["id"], delta=1)
                        add_ledger_entry(
                            sb,
                            week=week,
                            direction="out",
                            amount=float(e.get("cost") or 0),
                            category="diplomacy_equipment",
                            note=f"Bought {e['name']}",
                            metadata={"equipment_id": e["id"]},
                        )
                        log_action(
                            sb,
                            category=UNDO_CATEGORY,
                            action="buy_diplomacy_equipment",
                            payload={"equipment_id": e["id"], "label": e["name"], "cost": float(e.get("cost") or 0)},
                        )
                        log_activity(sb, kind="diplomacy", message=f"Bought equipment: {e['name']}", meta={"equipment_id": e["id"], "week": week})
                        st.success("Purchased.")
                        st.rerun()


# ---------- Missions ----------
with tab_missions:
    st.subheader("Diplomacy Missions")
    st.caption("Players can dispatch units; the DM resolves the outcome.")

    if not units:
        st.warning("Seed diplomacy units first.")
        st.stop()

    # Only show unit types that have at least 1 available this week
    avail_rows = []
    for u in units:
        owned_qty = int(roster_map.get(u["id"], {}).get("quantity", 0))
        available = max(0, owned_qty - int(active_assigned.get(u["id"], 0)))
        if available > 0:
            avail_rows.append(u)
    unit_pool = avail_rows if avail_rows else units
    unit_options = {u["name"]: u for u in unit_pool}
    with st.expander("➕ Create mission", expanded=True):
        u_name = st.selectbox("Unit type", list(unit_options.keys()))
        u = unit_options[u_name]
        owned_qty = int(roster_map.get(u["id"], {}).get("quantity", 0))
        available = max(0, owned_qty - int(active_assigned.get(u["id"], 0)))

        qty = st.number_input(
            "Quantity to dispatch",
            min_value=1,
            max_value=max(1, available),
            value=1,
            step=1,
            disabled=available <= 0,
        )
        target = st.text_input("Target (region/faction)", value="")
        objective = st.text_area("Objective", value="")
        eta_week = st.number_input("Suggested return week (DM can change)", min_value=week, value=week, step=1)

        # Equipment assignment (simple: choose quantities per item, limited by inventory)
        assignment: dict[str, int] = {}
        if equip_items:
            st.markdown("**Assign equipment (optional)**")
            cols = st.columns(2)
            for i, e in enumerate(equip_items):
                owned = int(equip_inv.get(e["id"], 0))
                with cols[i % 2]:
                    q = st.number_input(
                        f"{e['name']} (owned: {owned})",
                        min_value=0,
                        max_value=max(0, owned),
                        value=0,
                        step=1,
                        key=f"assign_{e['id']}",
                    )
                    if q:
                        assignment[e["id"]] = int(q)

        base_success = float(u.get("success") or 0.0)
        infra_bonus = float(success_bonus_pct_for_category(sb, "diplomacy"))
        bonus_success = compute_equipment_bonus_pct(equip_items, assignment) + infra_bonus
        total_success = max(0.0, min(95.0, base_success + bonus_success))
        st.info(
            f"Calculated success chance: **{total_success:.0f}%** (base {base_success:.0f}% + bonuses {bonus_success:.0f}% | infra {infra_bonus:.0f}% + equipment {(bonus_success-infra_bonus):.0f}%)"
        )

        can_dispatch = available > 0 and target.strip() and objective.strip()
        if st.button("Dispatch mission", disabled=not can_dispatch):
            create_mission(
                sb,
                table="diplomacy_missions",
                week=week,
                unit_id=u["id"],
                quantity=int(qty),
                target=target.strip(),
                objective=objective.strip(),
                base_success=base_success,
                bonus_success=bonus_success,
                eta_week=int(eta_week),
                equipment_assignment=assignment,
            )
            log_activity(
                sb,
                kind="diplomacy",
                message=f"Dispatched {qty}× {u['name']} on a mission",
                meta={"unit_id": u["id"], "qty": int(qty), "target": target.strip(), "week": week},
            )
            st.success("Mission dispatched.")
            st.rerun()

    st.divider()

    missions = list_missions(sb, "diplomacy_missions", week)
    if not missions:
        st.info("No missions this week.")
    else:
        # Join unit names
        unit_name_by_id = {u["id"]: u["name"] for u in units}
        rows = []
        for m in missions:
            rows.append(
                {
                    "Status": m.get("status"),
                    "Unit": unit_name_by_id.get(m.get("unit_id"), "Unknown"),
                    "Qty": int(m.get("quantity") or 0),
                    "Target": m.get("target") or "",
                    "Objective": m.get("objective") or "",
                    "ETA Week": m.get("eta_week"),
                    "Chance": f"{float(m.get('total_success') or 0):.0f}%",
                    "Roll": m.get("roll"),
                    "Success": m.get("success"),
                    "Note": m.get("resolution_note") or "",
                    "_id": m.get("id"),
                }
            )

        df = pd.DataFrame(rows)
        st.dataframe(df.drop(columns=["_id"]), use_container_width=True, hide_index=True)

        # DM resolution controls
        with st.expander("🔒 DM: Resolve a mission"):
            active = [r for r in rows if r["Status"] == "active"]
            if not active:
                st.info("No active missions to resolve.")
            else:
                labels = [f"{r['Unit']} → {r['Target']} ({r['Qty']})" for r in active]
                choice = st.selectbox("Select active mission", labels)
                selected = active[labels.index(choice)]
                dm_note = st.text_area("DM note", value="")
                if st.button("Resolve selected", key="resolve_dipl"):
                    if not dm_gate("DM password required to resolve missions", key="dipl_resolve"):
                        st.stop()
                    res = resolve_mission(sb, table="diplomacy_missions", mission_id=selected["_id"], dm_note=dm_note)
                    log_activity(
                        sb,
                        kind="diplomacy",
                        message=f"Resolved mission: {choice}",
                        meta={"mission_id": selected["_id"], "roll": res.get("roll"), "success": res.get("success")},
                    )
                    st.success(f"Resolved. Roll {res['roll']} vs {res['total_success']:.0f}% → {'SUCCESS' if res['success'] else 'FAILURE'}")
                    st.rerun()


st.info("Upkeep is applied during the weekly tick (Advance Week).")
