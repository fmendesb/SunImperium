import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week, set_current_week, add_ledger_entry
from utils import economy
from utils.nav import hide_default_sidebar_nav

# 🔒 hide Streamlit's native page navigation
hide_default_sidebar_nav()

st.set_page_config(
    page_title="DM Console",
    page_icon="🔮",
    layout="wide",
)

sb = get_supabase()
ensure_bootstrap(sb)

week = get_current_week(sb)

st.title("🔮 DM Console")
st.caption(f"Controls · Current week: {week}")
st.divider()

# -------------------------
# Admin Event Log
# -------------------------
st.subheader("Admin Event Log")
st.caption("Last 50 logged actions (best-effort).")
try:
    logs = (
        sb.table("activity_log")
        .select("created_at,kind,message")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
        .data
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
    st.info("activity_log table not present in this schema.")

st.divider()

# -------------------------
# Player Visibility Controls (Pages)
# -------------------------
st.subheader("Player Visibility Controls")
st.caption("Hide or reveal pages for players. DM always sees everything.")

if not dm_gate("DM password required to change visibility settings", key="vis_gate"):
    st.warning("Locked.")
else:
    # Load current hidden set (best-effort)
    hidden_pages: list[str] = []
    has_ui_hidden = True
    try:
        app_state = (
            sb.table("app_state")
            .select("id,ui_hidden_pages")
            .eq("id", 1)
            .limit(1)
            .execute()
            .data
            or []
        )
        if app_state and isinstance(app_state[0].get("ui_hidden_pages"), list):
            hidden_pages = app_state[0].get("ui_hidden_pages") or []
        else:
            hidden_pages = []
    except Exception:
        has_ui_hidden = False

    if not has_ui_hidden:
        st.warning(
            "Your database does not have `app_state.ui_hidden_pages` yet.\n"
            "Run the SQL migration I provided to add it, then refresh."
        )
    else:
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
        ]

        df_pages = pd.DataFrame(
            [{"Page file": p, "Hidden from players": (p in hidden_pages)} for p in known_pages]
        )

        st.caption("Tip: checked = hidden. Unchecked = visible to players.")
        edited = st.data_editor(
            df_pages,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Page file": st.column_config.TextColumn(disabled=True),
                "Hidden from players": st.column_config.CheckboxColumn(),
            },
            key="pages_visibility_editor",
        )

        if st.button("Save page visibility", type="primary"):
            try:
                new_hidden = [
                    df_pages.iloc[i]["Page file"]
                    for i, row in edited.iterrows()
                    if bool(row["Hidden from players"])
                ]
                sb.table("app_state").upsert({"id": 1, "ui_hidden_pages": new_hidden}).execute()
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save: {e}")

st.divider()

# -------------------------
# Advance Week
# -------------------------
st.subheader("Advance Week")

if not dm_gate("Advance Week (DM)", key="advance_gate"):
    st.warning("Locked.")
else:
    st.write("Computes economy, posts payout and upkeep to the ledger, closes the current week, and opens the next.")

    manual_income = st.number_input("Manual income adjustment (optional)", value=0.0, step=10.0)

    if st.button("✅ Advance Week", type="primary"):
        # Compute economy for current week, write outputs
        summary, per_item = economy.compute_week_economy(sb, week)
        economy.write_week_economy(sb, summary, per_item)

        # Post payout
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

        # Close week and open next
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

        # Carry forward reputation rows
        try:
            reps = sb.table("reputation").select("faction_id,score,dc,bonus,note").eq("week", week).execute().data or []
            for r in reps:
                sb.table("reputation").upsert(
                    {
                        "week": next_week,
                        "faction_id": r["faction_id"],
                        "score": r.get("score", 0),
                        "dc": r.get("dc"),
                        "bonus": r.get("bonus"),
                        "note": r.get("note", "") or "carried",
                    },
                    on_conflict="week,faction_id",
                ).execute()
        except Exception:
            pass

        st.success(f"Advanced to Week {next_week}.")
        st.rerun()
