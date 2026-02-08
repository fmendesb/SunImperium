import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils.dm import dm_gate


def dc_bonus_from_score(score: int) -> tuple[int, int]:
    """Monotonic mapping: higher reputation -> lower DC, higher bonus.

    Adjust the tables to match your exact canon if needed.
    """
    score = int(score)
    score = max(0, min(10, score))
    dc_table = {0: 20, 1: 19, 2: 18, 3: 17, 4: 16, 5: 15, 6: 14, 7: 13, 8: 12, 9: 11, 10: 10}
    bonus_table = {0: -3, 1: -2, 2: -1, 3: 0, 4: 1, 5: 2, 6: 3, 7: 4, 8: 5, 9: 6, 10: 7}
    return dc_table[score], bonus_table[score]


page_config("Silver Council | Reputation", "📜")
sidebar("📜 Reputation")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("📜 Reputation")
st.caption(f"Week {week}")

is_dm = dm_gate("DM password required to edit reputation", key="rep")

# Load factions (these are the 'possible reputations')
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
    factions = (
        sb.table("factions")
        .select("id,name,type")
        .order("type")
        .order("name")
        .execute()
        .data
        or []
    )

if not factions:
    st.warning("No factions found. Seed the `factions` table first.")
    st.stop()

show_hidden = False
if is_dm:
    show_hidden = st.toggle("Show hidden reputations (DM)", value=False)

if not show_hidden:
    factions = [f for f in factions if not bool(f.get("is_hidden", False))]

faction_ids = [f["id"] for f in factions]

reps = (
    sb.table("reputation")
    .select("week,faction_id,score,dc,bonus,note")
    .eq("week", week)
    .execute()
    .data
    or []
)
rep_map = {r["faction_id"]: r for r in reps}

rows = []
for f in factions:
    r = rep_map.get(f["id"], {})
    score = int(r.get("score") or 0)
    dc, bonus = dc_bonus_from_score(score)
    rows.append(
        {
            "Name": f.get("name"),
            "Type": f.get("type"),
            "Score": score,
            "DC": dc,
            "Bonus": bonus,
            "Notes": r.get("note") or "",
            "_faction_id": f["id"],
        }
    )

df = pd.DataFrame(rows)

st.subheader("Reputation Table")
st.caption("DC and Bonus are derived from Score and update automatically on save.")

edited = st.data_editor(
    df.drop(columns=["_faction_id"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Name": st.column_config.TextColumn(disabled=True),
        "Type": st.column_config.TextColumn(disabled=True),
        "DC": st.column_config.NumberColumn(disabled=True),
        "Bonus": st.column_config.NumberColumn(disabled=True),
        "Score": st.column_config.NumberColumn(step=1, min_value=0, max_value=10, disabled=not is_dm),
        "Notes": st.column_config.TextColumn(disabled=not is_dm),
    },
    key="rep_editor",
)

if st.button("Save", type="primary", disabled=not is_dm):
    try:
        for i, row in edited.iterrows():
            faction_id = df.iloc[i]["_faction_id"]
            score = int(row["Score"])
            note = str(row.get("Notes") or "").strip()
            dc, bonus = dc_bonus_from_score(score)

            sb.table("reputation").upsert(
                {
                    "week": week,
                    "faction_id": faction_id,
                    "score": score,
                    "dc": dc,
                    "bonus": bonus,
                    "note": note,
                },
                on_conflict="week,faction_id",
            ).execute()

        st.success("Saved.")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to save: {e}")
