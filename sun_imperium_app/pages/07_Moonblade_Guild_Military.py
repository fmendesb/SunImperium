import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals, add_ledger_entry
from utils.undo import log_action, get_last_action, pop_last_action
from utils.squads import detect_member_caps, fetch_members, bulk_add_members

UNDO_CATEGORY = "moonblade"

page_config("Moonblade Guild | Military", "⚔️")
sidebar("⚔ Military")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

tot = compute_totals(sb, week=week)

st.title("⚔️ Moonblade Guild")
st.caption(f"Military · Week {week} · Moonvault: {tot.gold:,.0f} gold")

# -------------------------
# Undo
# -------------------------
with st.popover("↩️ Undo (Moonblade)"):
    last = get_last_action(sb, category=UNDO_CATEGORY)
    if not last:
        st.write("No actions to undo.")
    else:
        payload = last.get("payload") or {}
        st.write(f"Last: {last.get('action','')} · {payload.get('name','')}")
        if st.button("Undo last", key="undo_moonblade"):
            if last.get("action") == "recruit_unit":
                unit_id = payload.get("unit_id")
                qty = int(payload.get("qty") or 0)
                refund = float(payload.get("cost") or 0)

                if unit_id and qty:
                    roster = (
                        sb.table("moonblade_roster")
                        .select("quantity")
                        .eq("unit_id", unit_id)
                        .limit(1)
                        .execute()
                        .data
                    )
                    if roster:
                        new_qty = max(0, int(roster[0]["quantity"]) - qty)
                        sb.table("moonblade_roster").upsert({"unit_id": unit_id, "quantity": new_qty}).execute()

                if refund:
                    add_ledger_entry(
                        sb,
                        week=week,
                        direction="in",
                        amount=refund,
                        category="undo_refund",
                        note="Undo: recruit unit",
                    )

                pop_last_action(sb, action_id=last["id"])
                st.success("Undone.")
                st.rerun()
            else:
                st.error("Undo not implemented for this action type yet.")

st.divider()

# -------------------------
# Load units + roster once
# -------------------------
units = (
    sb.table("moonblade_units")
    .select("id,name,unit_type,power,cost,upkeep,description")
    .order("unit_type")
    .order("name")
    .execute()
    .data
    or []
)

roster_rows = sb.table("moonblade_roster").select("unit_id,quantity").execute().data or []
roster_map = {r["unit_id"]: int(r.get("quantity") or 0) for r in roster_rows}
unit_by_id = {u["id"]: u for u in units}

# -------------------------
# Tabs
# -------------------------
tab_units, tab_squads = st.tabs(["🛡️ Units", "👥 Squads"])

# =========================
# Units
# =========================
with tab_units:
    st.subheader("Recruitment")

    if not units:
        st.warning("No Moonblade units seeded yet. Seed `moonblade_units` from Excel.")
    else:
        unit_types = sorted({(u.get("unit_type") or "Other").strip() for u in units})
        filt_cols = st.columns([2, 3, 2])
        with filt_cols[0]:
            type_filter = st.selectbox("Filter by unit type", ["All"] + unit_types, key="unit_type_filter")
        with filt_cols[1]:
            text_filter = st.text_input("Search", value="", placeholder="Type a name...", key="unit_search")
        with filt_cols[2]:
            owned_only = st.checkbox("Show owned only", value=False)

        def _match(u: dict) -> bool:
            if type_filter != "All" and (u.get("unit_type") or "Other").strip() != type_filter:
                return False
            if owned_only and roster_map.get(u["id"], 0) <= 0:
                return False
            if text_filter.strip():
                return text_filter.strip().lower() in (u.get("name") or "").lower()
            return True

        shown = [u for u in units if _match(u)]
        if not shown:
            st.info("No units match your filters.")
        else:
            for u in shown:
                with st.container(border=True):
                    left, right = st.columns([3, 1])
                    with left:
                        st.write(f"**{u['name']}**")
                        st.caption(u.get("description") or "")
                        st.write(
                            f"Type: {(u.get('unit_type') or 'Other')} · "
                            f"Cost: {float(u.get('cost') or 0):,.0f} · "
                            f"Upkeep: {float(u.get('upkeep') or 0):,.0f} · "
                            f"Power: {float(u.get('power') or 0):,.0f}"
                        )
                        st.write(f"Owned: {roster_map.get(u['id'], 0)}")

                    with right:
                        qty = st.number_input(
                            "Qty",
                            min_value=1,
                            max_value=999,
                            value=1,
                            key=f"qty_{u['id']}",
                        )
                        total_cost = float(u.get("cost") or 0) * int(qty)
                        if st.button("Recruit", key=f"recruit_{u['id']}", disabled=tot.gold < total_cost):
                            new_qty = roster_map.get(u["id"], 0) + int(qty)
                            sb.table("moonblade_roster").upsert({"unit_id": u["id"], "quantity": new_qty}).execute()

                            add_ledger_entry(
                                sb,
                                week=week,
                                direction="out",
                                amount=total_cost,
                                category="moonblade_recruit",
                                note=f"Recruited {qty}x {u['name']}",
                                metadata={"unit_id": u["id"], "qty": int(qty)},
                            )
                            log_action(
                                sb,
                                category=UNDO_CATEGORY,
                                action="recruit_unit",
                                payload={"unit_id": u["id"], "qty": int(qty), "cost": total_cost, "name": u["name"]},
                            )
                            st.success("Recruited.")
                            st.rerun()

# =========================
# Squads
# =========================
with tab_squads:
    st.subheader("Squads")
    st.caption("Create squads and assign owned units. Squad power is computed from unit power × quantity.")

    # Friendly squads only
    try:
        squads = (
            sb.table("squads")
            .select("id,name,region,destination,mission,status,deployed_week,is_enemy")
            .eq("is_enemy", False)
            .order("name")
            .execute()
            .data
            or []
        )
    except Exception:
        squads = sb.table("squads").select("id,name,region").order("name").execute().data or []

    with st.form("create_squad", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            squad_name = st.text_input("New squad name")
        with c2:
            region = st.text_input("Home region (optional)", placeholder="New Triport")
        with c3:
            destination = st.text_input("Deployed to (optional)", placeholder="Amnesty")
        mission = st.text_input("Mission (optional)", placeholder="Patrol / Escort / Siege...")
        if st.form_submit_button("Create squad"):
            if squad_name.strip():
                payload = {"name": squad_name.strip(), "region": region.strip() or None}
                # optional newer fields
                payload["destination"] = destination.strip() or None
                payload["mission"] = mission.strip() or None
                payload["status"] = "ready"
                payload["deployed_week"] = None
                payload["is_enemy"] = False
                try:
                    sb.table("squads").insert(payload).execute()
                except Exception:
                    # fallback: only the old columns exist
                    sb.table("squads").insert({"name": squad_name.strip(), "region": region.strip() or None}).execute()
                st.success("Squad created.")
                st.rerun()

    if not squads:
        st.info("No squads yet. Create one above.")
        st.stop()

    squad_options = {s["name"]: s for s in squads}
    label = st.selectbox("Select squad", list(squad_options.keys()), key="squad_select")
    squad = squad_options[label]

    # Load squad members (schema-tolerant)
    caps = detect_member_caps(sb)
    UNIT_TYPE_BY_ID = {u.get("id"): (u.get("unit_type") or "Other") for u in units}
    members, _caps = fetch_members(sb, squad["id"], unit_type_by_id=UNIT_TYPE_BY_ID, _caps=caps)

    def compute_squad_power(ms: list[dict]) -> float:
        power_total = 0.0
        for m in ms:
            qty = int(m.get("quantity") or 0)
            uid = m.get("unit_id")
            if uid and uid in unit_by_id:
                p = float(unit_by_id[uid].get("power") or 0)
            else:
                # fallback: unknown unit_id, approximate
                p = 1.0
            power_total += p * qty
        return power_total

    st.markdown(
        f"**{squad.get('name')}** · Region: {squad.get('region') or '—'} · "
        f"Power: **{compute_squad_power(members):,.1f}**"
    )

    # Mission / status editor
    with st.expander("📌 Deployment / Mission", expanded=False):
        cur_dest = (squad.get("destination") or "")
        cur_mis = (squad.get("mission") or "")
        cur_status = (squad.get("status") or "ready")

        dest = st.text_input("Deployed to", value=cur_dest, key="sq_dest")
        mis = st.text_input("Mission", value=cur_mis, key="sq_mis")
        status = st.selectbox("Status", ["ready", "deployed", "resting", "wounded"], index=["ready", "deployed", "resting", "wounded"].index(cur_status) if cur_status in ["ready", "deployed", "resting", "wounded"] else 0)

        if st.button("Save deployment", key="save_deploy"):
            try:
                sb.table("squads").update({
                    "destination": dest.strip() or None,
                    "mission": mis.strip() or None,
                    "status": status,
                    "deployed_week": week if status == "deployed" else None,
                }).eq("id", squad["id"]).execute()
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save (missing columns?): {e}")

    # Members table
    if members:
        mrows = []
        for m in members:
            uid = m.get("unit_id")
            u = unit_by_id.get(uid) if uid else None
            name = (u.get("name") if u else None) or (m.get("unit_type") or "Unknown")
            mrows.append(
                {
                    "Unit": name,
                    "Type": (u.get("unit_type") if u else m.get("unit_type") or "Other"),
                    "Qty": int(m.get("quantity") or 0),
                }
            )
        st.dataframe(pd.DataFrame(mrows), use_container_width=True, hide_index=True)
    else:
        st.caption("No members assigned yet.")

    st.markdown("#### Assign units")

    owned_units = [u for u in units if roster_map.get(u["id"], 0) > 0]
    if not owned_units:
        st.info("Recruit units first.")
    else:
        st.caption("Tip: enter quantities for multiple units, then click **Add selected** once.")

        df = pd.DataFrame(
            [
                {
                    "Unit": u.get("name"),
                    "Type": (u.get("unit_type") or "Other"),
                    "Owned": int(roster_map.get(u["id"], 0)),
                    "Power": float(u.get("power") or 0),
                    "Add": 0,
                    "_unit_id": u["id"],
                }
                for u in owned_units
            ]
        )

        # show user-facing table only
        view = df[["Unit", "Type", "Owned", "Power", "Add"]]
        edited = st.data_editor(
            view,
            hide_index=True,
            use_container_width=True,
            column_config={
                "Owned": st.column_config.NumberColumn(disabled=True),
                "Power": st.column_config.NumberColumn(disabled=True),
                "Add": st.column_config.NumberColumn(min_value=0, step=1),
            },
            key="squad_add_editor",
        )

        if st.button("Add selected", type="primary"):
            adds = []
            for i, row in edited.iterrows():
                add_qty = int(row.get("Add") or 0)
                if add_qty <= 0:
                    continue
                unit_id = df.iloc[i]["_unit_id"]
                owned = int(df.iloc[i]["Owned"])
                if add_qty > owned:
                    add_qty = owned
                adds.append(
                    {
                        "unit_id": unit_id,
                        "unit_type": str(df.iloc[i]["Type"]),
                        "qty": add_qty,
                    }
                )
                # decrement roster
                sb.table("moonblade_roster").upsert({"unit_id": unit_id, "quantity": owned - add_qty}).execute()

            if adds:
                bulk_add_members(sb, squad["id"], adds, caps)
                st.success("Assigned.")
                st.rerun()
            else:
                st.info("Nothing to add.")

st.info("War Simulator: pick a friendly squad and an enemy squad (DM-created) to resolve battles.")
