import streamlit as st

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week, set_current_week, add_ledger_entry
from utils import economy
from datetime import datetime, timezone

st.set_page_config(page_title="DM Console", page_icon="🔮", layout="wide")

sb = get_supabase()
try:
    ensure_bootstrap(sb)
except Exception:
    st.error("Supabase connection hiccup. Refresh and try again.")
    st.stop()
week = get_current_week(sb)

st.title("🔮 DM Console")
st.caption(f"Danger controls · Current week: {week}")

st.divider()

# Advance week
st.subheader("Advance Week")

if not dm_gate("Advance Week", key="advance_week"):
    st.warning("Locked.")
else:
    st.write("This computes weekly economy (production → tax → player payout), posts upkeep, then advances the week.")

    manual_income = st.number_input("Manual income adjustment (optional, adds to payout)", value=0.0, step=10.0)

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

        # --- Economy: compute production/tax payout for THIS week ---
        summary, per_item = economy.compute_week_economy(sb, week)

        # Upkeep total
        upkeep_total = infra_upkeep + mb_upkeep + db_upkeep + dip_upkeep
        summary.upkeep_total = float(upkeep_total)

        # Persist economy outputs
        economy.write_week_economy(sb, summary, per_item)

        payout = float(summary.player_payout) + float(manual_income or 0)
        if payout:
            add_ledger_entry(
                sb,
                week=week,
                direction="in",
                amount=payout,
                category="player_payout",
                note=f"Player share of taxes ({summary.tax_rate:.0%} tax, {summary.player_share:.0%} share)",
                metadata={
                    "gross_value": summary.gross_value,
                    "tax_income": summary.tax_income,
                    "player_payout": summary.player_payout,
                    "manual_adjustment": float(manual_income or 0),
                },
            )

        if infra_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(infra_upkeep), category="infrastructure_upkeep", note="Weekly infrastructure upkeep")
        if mb_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(mb_upkeep), category="moonblade_upkeep", note="Weekly Moonblade upkeep")
        if db_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(db_upkeep), category="dawnbreakers_upkeep", note="Weekly Dawnbreakers upkeep")
        if dip_upkeep:
            add_ledger_entry(sb, week=week, direction="out", amount=float(dip_upkeep), category="diplomacy_upkeep", note="Weekly diplomacy upkeep")

        # close week, increment
        sb.table("weeks").update({"closed_at": datetime.now(timezone.utc).isoformat()}).eq("week", week).execute()
        next_week = week + 1
        # open next week if missing
        wk = sb.table("weeks").select("week").eq("week", next_week).execute().data
        if not wk:
            sb.table("weeks").insert({"week": next_week, "opened_at": datetime.now(timezone.utc).isoformat(), "note": "auto-opened"}).execute()
        set_current_week(sb, next_week)

        # carry forward reputation scores (factions table)
        reps = sb.table("reputation").select("faction_id,score,dc,bonus,note").eq("week", week).execute().data
        if reps:
            for r in reps:
                sb.table("reputation").upsert(
                    {
                        "week": next_week,
                        "faction_id": r["faction_id"],
                        "score": r.get("score", 0),
                        "dc": r.get("dc"),
                        "bonus": r.get("bonus"),
                        "note": r.get("note", "") or "carried",
                    }
                ).execute()

        # carry forward region/family week state (so DM tweaks are per-week)
        for tbl, keycol in [("region_week_state", "region"), ("family_week_state", "family")]:
            rows = sb.table(tbl).select("*").eq("week", week).execute().data or []
            for row in rows:
                row2 = dict(row)
                row2["week"] = next_week
                # remove PK-only columns if present
                sb.table(tbl).upsert(row2).execute()

        st.success(f"Advanced to Week {next_week}.")
        st.rerun()
