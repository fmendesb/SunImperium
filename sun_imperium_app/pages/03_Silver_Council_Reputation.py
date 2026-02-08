import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils.undo import log_action, get_last_action, pop_last_action


def render():
    UNDO_CATEGORY = "reputation"


    sb = get_supabase()
    ensure_bootstrap(sb)
    week = get_current_week(sb)

    st.title("🗳️ The Silver Council")
    st.caption(f"Reputation · Week {week}")

    with st.popover("↩️ Undo (Reputation)"):
        last = get_last_action(sb, category=UNDO_CATEGORY)
        if not last:
            st.write("No reputation edits to undo.")
        else:
            payload = last["payload"] or {}
            st.write(f"Last: {last.get('action','')} · {payload.get('name','')}")
            if st.button("Undo last", key="undo_rep"):
                rep_id = payload.get("reputation_id")
                prev_score = payload.get("prev_score")
                if rep_id is not None and prev_score is not None:
                    sb.table("reputation").update({"score": prev_score}).eq("id", rep_id).execute()
                pop_last_action(sb, action_id=last["id"])
                st.success("Undone.")
                st.rerun()

    # Load factions and current reputation rows
    factions = sb.table("factions").select("id,name,type").order("type").order("name").execute().data
    reps = sb.table("reputation").select("id,faction_id,week,score,dc,bonus,note").eq("week", week).execute().data
    rep_by_faction = {r["faction_id"]: r for r in reps}

    if not factions:
        st.warning("No factions seeded yet. Seed `factions` table (from Excel or manually).")
        st.stop()

    rows = []
    for f in factions:
        r = rep_by_faction.get(f["id"])
        rows.append(
            {
                "faction_id": f["id"],
                "name": f["name"],
                "type": f["type"],
                "score": int(r["score"]) if r else 0,
                "dc": int(r["dc"]) if r and r.get("dc") is not None else None,
                "bonus": int(r["bonus"]) if r and r.get("bonus") is not None else None,
                "note": r.get("note") if r else "",
                "reputation_id": r["id"] if r else None,
            }
        )

    df = pd.DataFrame(rows)

    st.subheader("Edit reputation scores")
    st.caption("Edit the score. Status thresholds/labels are derived elsewhere.")

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "faction_id": st.column_config.TextColumn("faction_id", disabled=True, width="small"),
            "reputation_id": st.column_config.TextColumn("reputation_id", disabled=True, width="small"),
            "name": st.column_config.TextColumn("Name", disabled=True),
            "type": st.column_config.TextColumn("Type", disabled=True),
            "score": st.column_config.NumberColumn("Reputation", step=1),
            "dc": st.column_config.NumberColumn("DC", step=1),
            "bonus": st.column_config.NumberColumn("Bonus", step=1),
            "note": st.column_config.TextColumn("Note"),
        },
        key="rep_editor",
    )

    if st.button("Save changes"):
        # Compare with original and upsert
        for _, row in edited.iterrows():
            fid = row["faction_id"]
            rid = row["reputation_id"]
            payload = {
                "faction_id": fid,
                "week": week,
                "score": int(row["score"]),
                "dc": int(row["dc"]) if pd.notna(row["dc"]) else None,
                "bonus": int(row["bonus"]) if pd.notna(row["bonus"]) else None,
                "note": str(row["note"] or ""),
            }
            if rid:
                # log previous score for undo
                prev = rep_by_faction.get(fid)
                prev_score = int(prev["score"]) if prev else 0
                if prev_score != payload["score"]:
                    log_action(
                        sb,
                        category=UNDO_CATEGORY,
                        action="edit_reputation",
                        payload={"reputation_id": rid, "prev_score": prev_score, "name": row["name"]},
                    )
                sb.table("reputation").update(payload).eq("id", rid).execute()
            else:
                sb.table("reputation").insert(payload).execute()

        st.success("Saved.")
        st.rerun()
