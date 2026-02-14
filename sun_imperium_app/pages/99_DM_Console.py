import streamlit as st
import pandas as pd
from datetime import datetime, timezone
import re

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week, set_current_week, add_ledger_entry
from utils import economy

page_config("DM Console", "🔮")
sidebar("🔮 DM Console")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("🔮 DM Console")
st.caption(f"Controls · Current week: {week}")

unlocked = dm_gate("DM password required", key="dm_console")

# -------------------------
# Admin Event Log
# -------------------------
st.divider()
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

# -------------------------
# Visibility + Enemy tools
# -------------------------
st.divider()
st.subheader("DM Controls")

if not unlocked:
    st.warning("Locked.")
    st.stop()

vis_tab, reps_tab, enemy_tab, week_tab = st.tabs(
    ["🫥 Hide Pages", "🫥 Hide Reputations", "🧟 Enemy Squads", "⏳ Advance Week"]
)

# --- Hide pages ---
with vis_tab:
    st.caption("Hide pages from players. DM always sees everything.")

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
            "Run the SQL migration to add it, then refresh."
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

        st.caption("Checked = hidden. Unchecked = visible.")
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

# --- Hide reputations (factions) ---
with reps_tab:
    st.caption("Hide faction reputations from players (factions.is_hidden).")

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

        if st.button("Save reputation visibility", type="primary"):
            try:
                for i, row in edited_f.iterrows():
                    fid = df_f.iloc[i]["_id"]
                    sb.table("factions").update({"is_hidden": bool(row["Hidden from players"]) }).eq("id", fid).execute()
                st.success("Saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save: {e}")
    else:
        st.info("No factions found.")

# --- Enemy squads ---
with enemy_tab:
    st.caption(
        "Create DM-controlled enemy squads for the War Simulator.\n"
        "They reuse the same Moonblade unit catalog so power math stays consistent."
    )

    # Load units
    units = (
        sb.table("moonblade_units")
        .select("id,name,unit_type,power,cost,upkeep")
        .order("unit_type")
        .order("name")
        .execute()
        .data
        or []
    )

    if not units:
        st.warning("No moonblade_units seeded yet.")
    else:
        # Existing enemy squads
        try:
            enemy_squads = (
                sb.table("squads")
                .select("id,name,region,is_enemy")
                .eq("is_enemy", True)
                .order("name")
                .execute()
                .data
                or []
            )
        except Exception:
            enemy_squads = []
            st.warning(
                "Your squads table does not appear to have `is_enemy` yet. "
                "Run the SQL migration included in this patch, then refresh."
            )

        with st.form("create_enemy_squad", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                squad_name = st.text_input("Enemy squad name")
            with c2:
                region = st.text_input("Region (optional)")
            if st.form_submit_button("Create enemy squad"):
                if not squad_name.strip():
                    st.error("Please enter a name.")
                else:
                    # Robust insert: some schemas have extra NOT NULL columns (week/owner/type/etc.)
                    def _infer_missing_notnull_column(err: Exception) -> str | None:
                        txt = str(err)
                        m = re.search(r'null value in column "([^"]+)"', txt)
                        return m.group(1) if m else None

                    def _default_for_col(col: str) -> object:
                        c = col.lower()
                        if c in {"week", "created_week", "start_week"}:
                            return int(week)
                        if c in {"deployed_week"}:
                            return None
                        if c in {"is_enemy"}:
                            return True
                        if c in {"status"}:
                            return "ready"
                        if c in {"side", "squad_side", "type", "squad_type"}:
                            return "enemy"
                        if c in {"owner", "created_by"}:
                            return "dm"
                        if c in {"destination", "mission", "region"}:
                            return None
                        return None

                    payload = {
                        "name": squad_name.strip(),
                        "region": region.strip() or None,
                        "is_enemy": True,
                        "status": "ready",
                        "deployed_week": None,
                    }

                    last_err: Exception | None = None
                    for _ in range(6):
                        try:
                            sb.table("squads").insert(payload).execute()
                            last_err = None
                            break
                        except Exception as e:
                            last_err = e
                            missing = _infer_missing_notnull_column(e)
                            if missing and missing not in payload:
                                payload[missing] = _default_for_col(missing)
                                continue
                            # Legacy fallback
                            try:
                                sb.table("squads").insert({"name": squad_name.strip(), "region": region.strip() or None, "is_enemy": True}).execute()
                                last_err = None
                            except Exception as e2:
                                last_err = e2
                            break

                    if last_err:
                        st.error(f"Could not create enemy squad: {last_err}")
                    else:
                        st.success("Enemy squad created.")
                        st.rerun()

        if not enemy_squads:
            st.info("No enemy squads yet. Create one above.")
        else:
            squad = st.selectbox(
                "Select enemy squad",
                options=enemy_squads,
                format_func=lambda r: r.get("name") or "(unnamed)",
            )

            members = (
                sb.table("squad_members")
                .select("id,unit_id,unit_type,quantity")
                .eq("squad_id", squad["id"])
                .execute()
                .data
                or []
            )

            unit_by_id = {u["id"]: u for u in units}
            rows = []
            for m in members:
                u = unit_by_id.get(m.get("unit_id"))
                nm = u["name"] if u else (m.get("unit_type") or "Other")
                rows.append({"Unit": nm, "Type": m.get("unit_type"), "Qty": int(m.get("quantity") or 0)})

            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No members yet.")

            st.markdown("#### Add units")
            pick = st.selectbox(
                "Unit",
                options=units,
                format_func=lambda u: f"{u['name']} ({u.get('unit_type') or 'Other'})",
                key="enemy_pick_unit",
            )
            qty_add = st.number_input("Add qty", min_value=1, max_value=999, value=1, key="enemy_add_qty")

            if st.button("Add to enemy squad", key="enemy_add_btn"):
                # best-effort: emulate composite upsert
                existing = (
                    sb.table("squad_members")
                    .select("id,quantity")
                    .eq("squad_id", squad["id"])
                    .eq("unit_id", pick["id"])
                    .limit(1)
                    .execute()
                    .data
                )
                if existing:
                    sb.table("squad_members").update(
                        {"quantity": int(existing[0]["quantity"]) + int(qty_add)}
                    ).eq("id", existing[0]["id"]).execute()
                else:
                    sb.table("squad_members").insert(
                        {
                            "squad_id": squad["id"],
                            "unit_id": pick["id"],
                            "unit_type": (pick.get("unit_type") or "Other"),
                            "quantity": int(qty_add),
                        }
                    ).execute()
                st.success("Added.")
                st.rerun()

# --- Advance week ---
with week_tab:
    st.caption("Computes economy, posts payout to the ledger, closes the week, opens next week.")

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

        # Carry forward population (survival can reduce it)
        try:
            pop_now = int(getattr(summary, "population", 450_000) or 450_000)
            surv = float(getattr(summary, "survival_ratio", 1.0) or 1.0)
            pop_next = max(0, int(round(pop_now * surv)))
            sb.table("population_state").upsert({"week": next_week, "population": pop_next}, on_conflict="week").execute()
        except Exception:
            pass

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
