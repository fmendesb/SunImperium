import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.dm import dm_gate
from utils.equipment import (
    get_equipment_items,
    get_equipment_inventory,
    add_equipment,
    compute_equipment_bonus_pct,
)
from utils.missions import list_missions, create_mission, resolve_mission
from utils.activity import log_activity


st.set_page_config(page_title="Dawnbreakers | Intelligence", page_icon="🕵️", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)
tot = compute_totals(sb, week=week)

st.title("🕵️ Dawnbreakers: Intelligence")
st.caption(f"Week {week} · Moonvault: {tot.gold:,.0f} gold")


# ---------- Data ----------
units = (
    sb.table("dawnbreakers_units")
    .select("id,name,tier,purchase_cost,upkeep,success,description")
    .order("tier")
    .order("name")
    .execute()
    .data
    or []
)
roster_rows = sb.table("dawnbreakers_roster").select("id,unit_id,quantity").execute().data or []
roster_map = {r["unit_id"]: r for r in roster_rows}

equip_items = get_equipment_items(sb, "intelligence")
equip_inv = get_equipment_inventory(sb, "intelligence")

missions = list_missions(sb, "intelligence_missions", week)


def unit_kind(name: str) -> str:
    n = (name or "").lower()
    if "infiltrator" in n:
        return "Infiltrators"
    if "scout" in n:
        return "Scouts"
    if "spy" in n:
        return "Spies"
    return "Other"


def missions_qty_by_unit(active_only: bool = True):
    m = {}
    for row in missions:
        if active_only and str(row.get("status")) != "active":
            continue
        uid = row.get("unit_id")
        m[uid] = int(m.get(uid, 0)) + int(row.get("quantity") or 0)
    return m


active_assigned = missions_qty_by_unit(True)


tab_recruit, tab_equip, tab_missions = st.tabs(["Recruit", "Equipment", "Missions"])


# ---------- Recruit ----------
with tab_recruit:
    st.subheader("Recruit Operatives")
    st.caption("Use the filter to view Infiltrators, Scouts, or Spies grouped by tier.")

    if not units:
        st.warning("No intelligence units seeded yet.")
        st.stop()

    kinds = ["Infiltrators", "Scouts", "Spies", "All"]
    kind = st.selectbox("Filter", kinds, index=3)

    view_units = units
    if kind != "All":
        view_units = [u for u in units if unit_kind(u.get("name")) == kind]

    # Reorder: show same kind tiers together naturally (tier 1 -> 3)
    view_units = sorted(view_units, key=lambda x: (unit_kind(x.get("name")), int(x.get("tier") or 0)))

    for u in view_units:
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
                st.caption(f"Available: {available}")
                can_buy = tot.gold >= float(u["purchase_cost"])
                if st.button("Recruit", key=f"intel_recruit_{u['id']}", disabled=not can_buy):
                    row = roster_map.get(u["id"])
                    if row:
                        sb.table("dawnbreakers_roster").update({"quantity": owned_qty + 1}).eq("id", row["id"]).execute()
                    else:
                        sb.table("dawnbreakers_roster").insert({"unit_id": u["id"], "quantity": 1}).execute()

                    add_ledger_entry(
                        sb,
                        week=week,
                        direction="out",
                        amount=float(u["purchase_cost"]),
                        category="dawnbreakers_purchase",
                        note=f"Recruited {u['name']}",
                        metadata={"unit_id": u["id"]},
                    )
                    log_activity(sb, kind="intelligence", message=f"Recruited {u['name']}", meta={"unit_id": u["id"], "week": week})
                    st.success("Recruited.")
                    st.rerun()


# ---------- Equipment ----------
with tab_equip:
    st.subheader("Intelligence Equipment")
    st.caption("Equipment provides flat percentage bonuses to mission success.")

    if not equip_items:
        st.info("No intelligence equipment seeded yet. Add rows to mission_equipment (category='intelligence').")
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
                    if st.button("Buy", key=f"intel_buy_eq_{e['id']}", disabled=not can_buy):
                        add_equipment(sb, category="intelligence", equipment_id=e["id"], delta=1)
                        add_ledger_entry(
                            sb,
                            week=week,
                            direction="out",
                            amount=float(e.get("cost") or 0),
                            category="intelligence_equipment",
                            note=f"Bought {e['name']}",
                            metadata={"equipment_id": e["id"]},
                        )
                        log_activity(sb, kind="intelligence", message=f"Bought equipment: {e['name']}", meta={"equipment_id": e["id"], "week": week})
                        st.success("Purchased.")
                        st.rerun()


# ---------- Missions ----------
with tab_missions:
    st.subheader("Intelligence Missions")
    st.caption("Players can dispatch operatives; the DM resolves the outcome.")

    unit_options = {u["name"]: u for u in units}
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
                        key=f"intel_assign_{e['id']}",
                    )
                    if q:
                        assignment[e["id"]] = int(q)

        base_success = float(u.get("success") or 0.0)
        bonus_success = compute_equipment_bonus_pct(equip_items, assignment)
        total_success = max(0.0, min(95.0, base_success + bonus_success))
        st.info(f"Calculated success chance: **{total_success:.0f}%** (base {base_success:.0f}% + equipment {bonus_success:.0f}%)")

        can_dispatch = available > 0 and target.strip() and objective.strip()
        if st.button("Dispatch mission", disabled=not can_dispatch):
            create_mission(
                sb,
                table="intelligence_missions",
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
                kind="intelligence",
                message=f"Dispatched {qty}× {u['name']} on a mission",
                meta={"unit_id": u["id"], "qty": int(qty), "target": target.strip(), "week": week},
            )
            st.success("Mission dispatched.")
            st.rerun()

    st.divider()

    missions = list_missions(sb, "intelligence_missions", week)
    if not missions:
        st.info("No missions this week.")
    else:
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

        with st.expander("🔒 DM: Resolve a mission"):
            active = [r for r in rows if r["Status"] == "active"]
            if not active:
                st.info("No active missions to resolve.")
            else:
                labels = [f"{r['Unit']} → {r['Target']} ({r['Qty']})" for r in active]
                choice = st.selectbox("Select active mission", labels)
                selected = active[labels.index(choice)]
                dm_note = st.text_area("DM note", value="")
                if st.button("Resolve selected", key="resolve_intel"):
                    if not dm_gate("DM password required to resolve missions", key="intel_resolve"):
                        st.stop()
                    res = resolve_mission(sb, table="intelligence_missions", mission_id=selected["_id"], dm_note=dm_note)
                    log_activity(
                        sb,
                        kind="intelligence",
                        message=f"Resolved mission: {choice}",
                        meta={"mission_id": selected["_id"], "roll": res.get("roll"), "success": res.get("success")},
                    )
                    st.success(f"Resolved. Roll {res['roll']} vs {res['total_success']:.0f}% → {'SUCCESS' if res['success'] else 'FAILURE'}")
                    st.rerun()


st.info("Upkeep is applied during the weekly tick (Advance Week).")
