import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from utils.nav import hide_default_sidebar_nav
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week, set_current_week, add_ledger_entry
from utils import economy

hide_default_sidebar_nav()

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("🔮 DM Console")
st.caption(f"Controls · Current week: {week}")

unlocked = dm_gate("DM password required", key="dm_console")

st.divider()

# Admin Event Log
st.subheader("Admin Event Log")
try:
    logs = (
        sb.table("activity_log").select("created_at,kind,message").order("created_at", desc=True).limit(50).execute().data
        or []
    )
    if logs:
        df_logs = pd.DataFrame(
            [{"Time": l.get("created_at"), "Kind": l.get("kind"), "Message": l.get("message")} for l in logs]
        )
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
    else:
        st.info("No events logged yet.")
except Exception:
    st.info("activity_log table not present.")

st.divider()

# Visibility controls
st.subheader("Visibility Controls")
st.caption("Hide pages and reputations from players.")

if not unlocked:
    st.warning("Locked.")
else:
    tab_pages, tab_reps = st.tabs(["Hide Pages", "Hide Reputations"])

    with tab_pages:
        # Load current hidden pages from app_state
        hidden_pages = []
        try:
            app_state = (
                sb.table("app_state").select("id,ui_hidden_pages").eq("id", 1).limit(1).execute().data or []
            )
            if app_state and isinstance(app_state[0].get("ui_hidden_pages"), list):
                hidden_pages = app_state[0].get("ui_hidden_pages") or []
        except Exception:
            st.error("Missing app_state.ui_hidden_pages. Run the SQL migration that adds ui_hidden_pages.")

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
            "99_DM_Console.py",
        ]

        df_pages = pd.DataFrame(
            [{"Page": p, "Hidden from players": (p in hidden_pages)} for p in known_pages if p != "99_DM_Console.py"]
        )

        st.caption("Checked = hidden.")
        edited = st.data_editor(
            df_pages,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Page": st.column_config.TextColumn(disabled=True),
                "Hidden from players": st.column_config.CheckboxColumn(),
            },
            key="pages_editor",
        )

        if st.button("Save page visibility", type="primary"):
            new_hidden = [df_pages.iloc[i]["Page"] for i, row in edited.iterrows() if bool(row["Hidden from players"])]
            sb.table("app_state").upsert({"id": 1, "ui_hidden_pages": new_hidden}).execute()
            st.success("Saved.")
            st.rerun()

    with tab_reps:
        st.caption("Hides factions (reputations) via factions.is_hidden.")
        try:
            factions = sb.table("factions").select("id,name,type,is_hidden").order("type").order("name").execute().data or []
        except Exception:
            st.error("Missing factions.is_hidden column. Run the SQL migration that adds it.")
            factions = []

        if factions:
            df_f = pd.DataFrame(
                [
                    {
                        "Name": f.get("name"),
                        "Type": f.get("type"),
                        "Hidden from players": bool(f.get("is_hidden")),
                        "_id": f.get("id"),
                    }
                    for f in factions
                ]
            )
            edited_f = st.data_editor(
                df_f.drop(columns=["_id"]),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Name": st.column_config.TextColumn(disabled=True),
                    "Type": st.column_config.TextColumn(disabled=True),
                    "Hidden from players": st.column_config.CheckboxColumn(),
                },
                key="factions_editor",
            )

            if st.button("Save reputation visibility"):
                for i, row in edited_f.iterrows():
                    fid = df_f.iloc[i]["_id"]
                    sb.table("factions").update({"is_hidden": bool(row["Hidden from players"])}).eq("id", fid).execute()
                st.success("Saved.")
                st.rerun()

st.divider()

# Advance week
st.subheader("Advance Week")
st.caption("Computes economy, posts payout to the ledger, closes the week, opens next week.")

if not unlocked:
    st.warning("Locked.")
else:
    manual_income = st.number_input("Manual income adjustment (optional)", value=0.0, step=10.0)

    if st.button("✅ Advance Week", type="primary"):
        # Compute economy
        summary, per_item = economy.compute_week_economy(sb, week)
        economy.write_week_economy(sb, summary, per_item)

        payout = float(summary.player_payout) + float(manual_income or 0)
        if payout:
            add_ledger_entry(
                sb,
                week=week,
                direction="in",
                amount=payout,
                category="player_payout",
                note="Player share of taxes",
                metadata={
                    "gross_value": summary.gross_value,
                    "tax_income": summary.tax_income,
                    "player_payout": summary.player_payout,
                    "manual_adjustment": float(manual_income or 0),
                },
            )

        # Close current week
        try:
            sb.table("weeks").update({"closed_at": datetime.now(timezone.utc).isoformat()}).eq("week", week).execute()
        except Exception:
            pass

        next_week = week + 1

        # Ensure next week exists
        try:
            wk = sb.table("weeks").select("week").eq("week", next_week).execute().data
            if not wk:
                sb.table("weeks").insert({"week": next_week, "opened_at": datetime.now(timezone.utc).isoformat()}).execute()
        except Exception:
            pass

        set_current_week(sb, next_week)

        # Carry forward reputation
        try:
            reps = sb.table("reputation").select("faction_id,score,dc,bonus,note").eq("week", week).execute().data or []
            for r in reps:
                sb.table("reputation").upsert(
                    {
                        "week": next_week,
                        "faction_id": r["faction_id"],
                        "score": int(r.get("score") or 0),
                        "dc": r.get("dc"),
                        "bonus": r.get("bonus"),
                        "note": r.get("note") or "carried",
                    },
                    on_conflict="week,faction_id",
                ).execute()
        except Exception:
            pass

        st.success(f"Advanced to Week {next_week}.")
        st.rerun()
