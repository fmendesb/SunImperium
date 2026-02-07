import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils.undo import log_action, get_last_action, pop_last_action
from utils.dm import dm_gate
from utils.reputation_rules import derive_dc_bonus

UNDO_CATEGORY = "reputation"

st.set_page_config(page_title="Silver Council | Reputation", page_icon="🗳️", layout="wide")

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

st.subheader("Reputation")
view = st.radio(
    "Filter",
    options=["All", "Regions", "Families"],
    horizontal=True,
)
if view == "Regions":
    factions = [f for f in factions if str(f.get("type")) == "region"]
elif view == "Families":
    factions = [f for f in factions if str(f.get("type")) in {"house", "family"}]

if not factions:
    st.warning("No factions seeded yet. Seed `factions` table (from Excel or manually).")
    st.stop()

rows = []
for f in factions:
    r = rep_by_faction.get(f["id"])
    score = int(r["score"]) if r else 0
    derived = derive_dc_bonus(score)
    rows.append(
        {
            "name": f["name"],
            "type": f["type"],
            "score": score,
            "dc": derived.dc,
            "bonus": derived.bonus,
            "note": r.get("note") if r else "",
            "_faction_id": f["id"],
            "_reputation_id": r["id"] if r else None,
        }
    )

df = pd.DataFrame(rows)

st.subheader("Edit reputation scores")
st.caption(
    "Reputation scores are DM-controlled. DC and bonus are derived automatically from the score."
)

# Hide internal IDs from the UI, but keep them for saving.
display_df = df.drop(columns=["_faction_id", "_reputation_id"])

edited = st.data_editor(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "name": st.column_config.TextColumn("Name", disabled=True),
        "type": st.column_config.TextColumn("Type", disabled=True),
        "score": st.column_config.NumberColumn("Reputation", step=1),
        "dc": st.column_config.NumberColumn("DC", disabled=True),
        "bonus": st.column_config.NumberColumn("Bonus", disabled=True),
        "note": st.column_config.TextColumn("Note"),
    },
    key="rep_editor",
)

if st.button("Save changes"):
    if not dm_gate("DM password required to modify reputation", key="rep_save"):
        st.stop()

    # Compare with original and upsert
    for idx, row in edited.iterrows():
        fid = df.iloc[idx]["_faction_id"]
        rid = df.iloc[idx]["_reputation_id"]

        score = int(row["score"])
        derived = derive_dc_bonus(score)
        payload = {
            "faction_id": fid,
            "week": week,
            "score": score,
            "dc": derived.dc,
            "bonus": derived.bonus,
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
