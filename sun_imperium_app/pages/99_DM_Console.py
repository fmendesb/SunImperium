import streamlit as st
import pandas as pd

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

# -------------------------
# Admin Event Log
# -------------------------
st.subheader("Admin Event Log")
st.caption("Last 50 actions across modules (best-effort log via activity_log).")
try:
    logs = (
        sb.table("activity_log")
        .select("created_at,kind,message,meta")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
        or []
    )
    if logs:
        df_logs = pd.DataFrame(
            [
                {
                    "Time": l.get("created_at"),
                    "Kind": l.get("kind"),
                    "Message": l.get("message"),
                }
                for l in logs
            ]
        )
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("No events logged yet.")
except Exception:
    st.info("activity_log table not available in this schema.")

st.divider()

# -------------------------
# Player Visibility Controls
# -------------------------
st.subheader("Player Visibility Controls")

if not dm_gate("DM password required to change visibility settings", key="visibility_gate"):
    st.warning("Locked.")
else:
    tabs = st.tabs(["Hide Pages", "Hide Reputations (Factions)"])

    # ---- Hide Pages ----
    with tabs[0]:
        st.caption(
            "Hide or reveal sidebar pages for players. "
            "This uses app_state.ui_hidden_pages (if present)."
        )

        # Safe best-effort: if app_state/ui_hidden_pages is not available, do not crash.
        hidden_pages = []
        try:
            app_state = (
                sb.table("app_state")
                .select("id,ui_hidden_pages")
                .eq("id", 1)
                .limit(1)
                .execute()
                .data
            )
            if app_state and isinstance(app_state[0].get("ui_hidden_pages"), list):
                hidden_pages = app_state[0]["ui_hidden_pages"] or []
        except Exception:
            st.info("app_state.ui_hidden_pages not available in this schema yet.")
            hidden_pages = []

        # Enumerate known pages by file name (what Streamlit uses).
        # If you have custom navigation elsewhere, this still remains the source of truth.
        known_pages = [
            "01_Silver_Council_Dashboard.py",
            "02_Silver_Council_Infrastructure.py",
            "03_Silver_Council_Reputation.py",
            "04_Silver_Council_Legislation.py",
            "05_Silver_Council_Diplomacy.py",
            "06_Dawnbreakers_Intelligence.py",
            "07_Moonblade_Guild_Military.py",
            "08_War_Simulator.py",
            "09_Crafting_Hub.py",
            # DM Console intentionally excluded
        ]

        selected_hidden = st.multiselect(
            "Pages hidden from players",
            options=known_pages,
            default=[p for p in known_pages if p in hidden_pages],
            help="Players will not see these pages in the sidebar navigation (DM still can).",
        )

        if st.button("Save hidden pages", key="save_hidden_pages"):
            try:
                sb.table("app_state").upsert({"id": 1, "ui_hidden_pages": selected_hidden}).execute()
                st.success("Saved page visibility.")
            except Exception as e:
                st.error(f"Could not save hidden pages. Schema missing? Error: {e}")

    # ---- Hide Reputations (Factions) ----
    with tabs[1]:
        st.caption(
            "Hide specific reputations from players by hiding the underlying faction. "
            "Requires `factions.is_hidden` boolean column."
        )

        # Try loading factions with is_hidden, but do not crash if column not present.
        try:
            factions = (
                sb.table("factions")
                .select("id,name,type,is_hidden")
                .order("type")
                .order("name")
                .execute()
                .data
                or []
            )
            has_is_hidden = True
        except Exception:
            # Fallback: column doesn't exist yet
            factions = (
                sb.table("factions")
                .select("id,name,type")
                .order("type")
                .order("name")
                .execute()
                .data
                or []
            )
            has_is_hidden = False

        if not has_is_hidden:
            st.warning(
                "Missing column `factions.is_hidden`.\n\n"
                "Run this SQL in Supabase first:\n"
                "ALTER TABLE public.factions ADD COLUMN IF NOT EXISTS is_hidden boolean NOT NULL DEFAULT false;"
            )
        else:
            # Optional quick filters for DM convenience
            view = st.radio(
                "Filter",
                options=["All", "Regions", "Families"],
                horizontal=True,
                key="faction_hide_filter",
            )

            filtered = factions
            if view == "Regions":
                filtered = [f for f in factions if str(f.get("type")) == "region"]
            elif view == "Families":
                filtered = [f for f in factions if str(f.get("type")) in {"house", "family"}]

            if not filtered:
                st.info("No factions found for this filter.")
            else:
                df = pd.DataFrame(
                    [
                        {
                            "Name": f.get("name"),
                            "Type": f.get("type"),
                            "Hidden from players": bool(f.get("is_hidden")),
                            "_id": f.get("id"),
                        }
                        for f in filtered
                    ]
                )

                edited = st.data_editor(
                    df.drop(columns=["_id"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Name": st.column_config.TextColumn(disabled=True),
                        "Type": st.column_config.TextColumn(disabled=True),
                        "Hidden from players": st.column_config.CheckboxColumn(),
                    },
                    key="faction_hide_editor",
                )

                if st.button("Save reputation visibility", key="save_rep_visibility"):
                    # Apply updates row by row (safe, easy to audit)
                    try:
                        for i, row in edited.iterrows():
                            faction_id = df.iloc[i]["_id"]
                            desired_hidden = bool(row["Hidden from players"])
                            sb.table("factions").update({"is_hidden": desired_hidden}).eq("id", faction_id).execute()
                        st.success("Saved reputation visibility.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to save changes: {e}")

st.divider()

# -------------------------
# Advance week
# -------------------------
st.subheader("Advance Week")

wk_row = sb.table("weeks").select("closed_at").eq("week", week).limit(1).execute().data
already_closed = bool(wk_row and wk_row[0].get("closed_at"))
if already_closed:
    st.warning("This week is already marked closed. If you need to advance again, reopen the week manually in Supabase.")

if not dm_gate("Advance Week", key="advance_week"):
    st.warning("Locked.")
else:
    st.write("This computes weekly economy (production → tax → player payout), posts upkeep, then advances the week.")

    manual_income = st.number_input("Manual income adjustment (optional, adds to payout)", value=0.0, step=10.0)

    if st.button("✅ Advance Week", type="primary", disabled=already_closed):
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
        for tbl in ["region_week_state", "family_week_state"]:
            rows = sb.table(tbl).select("*").eq("week", week).execute().data or []
            for row in rows:
                row2 = dict(row)
                row2["week"] = next_week
                sb.table(tbl).upsert(row2).execute()

        st.success(f"Advanced to Week {next_week}.")
        st.rerun()
