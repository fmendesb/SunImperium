import streamlit as st
import pandas as pd

from utils.nav import sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week

sidebar("📜 Reputation")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("📜 Reputation")
st.caption(f"Week {week}")

# Identify DM state
is_dm = bool(st.session_state.get("is_dm", False))

# Filters
filter_view = st.radio("Show", ["All", "Regions", "Families"], horizontal=True)

# Hidden reputation handling:
# Players never see hidden factions. DM can manage visibility from DM Console.
show_hidden = False


def dc_bonus_from_score(score: int) -> tuple[int, int]:
    """Monotonic mapping: higher score => lower DC, higher bonus.

    Replace table if you have a canon mapping in your doc.
    """
    s = max(0, min(10, int(score)))
    dc_table = {0: 20, 1: 19, 2: 18, 3: 17, 4: 16, 5: 15, 6: 14, 7: 13, 8: 12, 9: 11, 10: 10}
    bonus_table = {0: -3, 1: -2, 2: -1, 3: 0, 4: 1, 5: 2, 6: 3, 7: 4, 8: 5, 9: 6, 10: 7}
    return dc_table[s], bonus_table[s]


# Load factions (the list of all reputations)
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

if filter_view == "Regions":
    factions = [f for f in factions if str(f.get("type")) == "region"]
elif filter_view == "Families":
    factions = [f for f in factions if str(f.get("type")) in {"family", "house"}]

if not show_hidden:
    factions = [f for f in factions if not bool(f.get("is_hidden", False))]

# Load current-week reputation rows
rep_rows = (
    sb.table("reputation")
    .select("week,faction_id,score,dc,bonus,note")
    .eq("week", week)
    .execute()
    .data
    or []
)
rep_map = {r["faction_id"]: r for r in rep_rows}

# Build UI dataframe (no IDs shown)
data = []
for f in factions:
    fid = f["id"]
    r = rep_map.get(fid, {})
    score = int(r.get("score") or 0)
    dc, bonus = dc_bonus_from_score(score)
    data.append(
        {
            "Faction": f.get("name"),
            "Type": f.get("type"),
            "Score": score,
            "DC": dc,
            "Notes": r.get("note") or "",
            "_faction_id": fid,
        }
    )

if not data:
    st.info("No reputations to display.")
    st.stop()

df = pd.DataFrame(data)

edited = st.data_editor(
    df.drop(columns=["_faction_id"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Faction": st.column_config.TextColumn(disabled=True),
        "Type": st.column_config.TextColumn(disabled=True),
        "DC": st.column_config.NumberColumn(disabled=True),
    },
    key="rep_editor",
)

if dm_gate("DM password required to save reputation changes", key="rep_save"):
    if st.button("💾 Save changes", type="primary"):
        try:
            for i, row in edited.iterrows():
                fid = df.iloc[i]["_faction_id"]
                score = int(row["Score"])
                note = str(row.get("Notes") or "").strip()
                dc, bonus = dc_bonus_from_score(score)

                sb.table("reputation").upsert(
                    {
                        "week": week,
                        "faction_id": fid,
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
else:
    st.info("View-only (DM locked).")
