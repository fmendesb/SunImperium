import streamlit as st

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week, set_current_week, add_ledger_entry

st.set_page_config(page_title="DM Console", page_icon="🔮", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("🔮 DM Console")
st.caption(f"Danger controls · Current week: {week}")

st.divider()

# Advance week
st.subheader("Advance Week")

if not dm_gate("Advance Week", key="advance_week"):
    st.warning("Locked.")
else:
    st.write("This posts weekly income and upkeep entries, closes the current week, then opens the next one.")

    manual_income = st.number_input("Manual income adjustment (optional)", value=0.0, step=10.0)

    if st.button("✅ Advance Week", type="primary"):
        # Compute upkeep from current owned assets
        infra_upkeep = 0.0
        owned_infra = sb.table("infrastructure_owned").select("infrastructure_id,owned").eq("owned", True).execute().data
        if owned_infra:
            infra_ids = [r["infrastructure_id"] for r in owned_infra]
            infra_rows = sb.table("infrastructure").select("id,upkeep").in_("id", infra_ids).execute().data
            infra_upkeep = sum(float(r.get("upkeep") or 0) for r in infra_rows)

        # Moonblade upkeep
        mb_upkeep = 0.0
        roster = sb.table("moonblade_roster").select("unit_id,quantity").execute().data
        if roster:
            unit_ids = [r["unit_id"] for r in roster]
            units = sb.table("moonblade_units").select("id,upkeep").in_("id", unit_ids).execute().data
            upkeep_map = {u["id"]: float(u.get("upkeep") or 0) for u in units}
            mb_upkeep = sum(float(r["quantity"]) * upkeep_map.get(r["unit_id"], 0.0) for r in roster)

        # Dawnbreakers upkeep
        db_upkeep = 0.0
        dbr = sb.table("dawnbreakers_roster").select("unit_id,quantity").execute().data
        if dbr:
            ids = [r["unit_id"] for r in dbr]
            units = sb.table("dawnbreakers_units").select("id,upkeep").in_("id", ids).execute().data
            upkeep_map = {u["id"]: float(u.get("upkeep") or 0) for u in units}
            db_upkeep = sum(float(r["quantity"]) * upkeep_map.get(r["unit_id"], 0.0) for r in dbr)

        # Diplomacy upkeep
        dip_upkeep = 0.0
        dipr = sb.table("diplomacy_roster").select("unit_id,quantity").execute().data
        if dipr:
            ids = [r["unit_id"] for r in dipr]
            units = sb.table("diplomacy_units").select("id,upkeep").in_("id", ids).execute().data
            upkeep_map = {u["id"]: float(u.get("upkeep") or 0) for u in units}
            dip_upkeep = sum(float(r["quantity"]) * upkeep_map.get(r["unit_id"], 0.0) for r in dipr)

        # TODO: resources_tax income from Market module. For now, manual only.
        if manual_income:
            add_ledger_entry(sb, week=week, direction="in", amount=float(manual_income), category="resources_tax", note="Manual weekly income")

        if infra_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(infra_upkeep), category="infrastructure_upkeep", note="Weekly infrastructure upkeep")
        if mb_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(mb_upkeep), category="moonblade_upkeep", note="Weekly Moonblade upkeep")
        if db_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(db_upkeep), category="dawnbreakers_upkeep", note="Weekly Dawnbreakers upkeep")
        if dip_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(dip_upkeep), category="diplomacy_upkeep", note="Weekly diplomacy upkeep")

        # close week, increment
        sb.table("weeks").update({"status": "closed"}).eq("week", week).execute()
        next_week = week + 1
        sb.table("weeks").upsert({"week": next_week, "status": "open"}).execute()
        set_current_week(sb, next_week)

        # carry forward reputation scores
        reps = sb.table("reputation").select("faction_id,score").eq("week", week).execute().data
        if reps:
            for r in reps:
                sb.table("reputation").upsert({"week": next_week, "faction_id": r["faction_id"], "score": r["score"], "note": "carried"}).execute()

        st.success(f"Advanced to Week {next_week}.")
        st.rerun()
