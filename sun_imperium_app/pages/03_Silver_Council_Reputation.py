import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week

# ✅ IMPORTANT: your DC/BONUS rule in one place
def dc_bonus_from_score(score: int) -> tuple[int, int]:
    """
    Adjust this mapping to match your doc precisely.
    This one is monotonic and fixes the bug you saw (3 and 7 both giving DC 15).
    Example: higher reputation => lower DC, higher bonus.
    """
    score = int(score)
    # Clamp expected range (edit if your range differs)
    score = max(0, min(10, score))

    # Example mapping (replace with your canon table if needed):
    # score: 0..10
    dc_table = {0:20, 1:19, 2:18, 3:17, 4:16, 5:15, 6:14, 7:13, 8:12, 9:11, 10:10}
    bonus_table = {0:-3, 1:-2, 2:-1, 3:0, 4:1, 5:2, 6:3, 7:4, 8:5, 9:6, 10:7}

    return dc_table[score], bonus_table[score]


st.set_page_config(page_title="Reputation", page_icon="📜", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)

week = get_current_week(sb)

st.title("📜 Reputation")
st.caption(f"Week {week}")

# --- DM detection (whatever your app uses) ---
is_dm = st.session_state.get("is_dm", False)

# --- Filters ---
filter_view = st.radio("Show", ["All", "Regions", "Families"], horizontal=True)

show_hidden = False
if is_dm:
    show_hidden = st.toggle("Show hidden reputations (DM only)", value=False)

# --- Load factions (includes is_hidden) ---
# NOTE: If your factions table uses different column names, adjust here.
factions = sb.table("factions").select("id,name,type,is_hidden").order("type").order("name").execute().data or []

# Apply Regions/Families filter
if filter_view == "Regions":
    factions = [f for f in factions if str(f.get("type")) == "region"]
elif filter_view == "Families":
    factions = [f for f in factions if str(f.get("type")) in {"family", "house"}]

# Apply hidden filter for players (and for DM unless they toggle show_hidden)
if not show_hidden:
    factions = [f for f in factions if not bool(f.get("is_hidden", False))]

visible_faction_ids = [f["id"] for f in factions]

# --- Load reputation rows for this week ---
rep_rows = sb.table("reputation").select("week,faction_id,score,dc,bonus,note").eq("week", week).execute().data or []

rep_map = {r["faction_id"]: r for r in rep_rows}

# --- Build dataframe for UI ---
data = []
for f in factions:
    r = rep_map.get(f["id"], {})
    score = int(r.get("score") or 0)
    dc, bonus = dc_bonus_from_score(score)

    # display uses computed DC/bonus (not stale stored values)
    data.append({
        "Faction": f.get("name"),
        "Type": f.get("type"),
        "Score": score,
        "DC": dc,
        "Bonus": bonus,
        "Notes": r.get("note") or "",
        "_faction_id": f["id"],
    })

df = pd.DataFrame(data)

if df.empty:
    st.info("No reputations to display with current filters.")
    st.stop()

st.caption("Score edits require DM password. DC/Bonus auto-update from Score.")

edited = st.data_editor(
    df.drop(columns=["_faction_id"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Faction": st.column_config.TextColumn(disabled=True),
        "Type": st.column_config.TextColumn(disabled=True),
        "DC": st.column_config.NumberColumn(disabled=True),
        "Bonus": st.column_config.NumberColumn(disabled=True),
    },
    key="rep_editor",
)

# --- Save ---
if dm_gate("DM password required to save reputation changes", key="rep_save_gate"):
    if st.button("💾 Save changes", type="primary"):
        try:
            # map edited rows back to faction ids by index
            for i, row in edited.iterrows():
                faction_id = df.iloc[i]["_faction_id"]
                score = int(row["Score"])
                note = str(row.get("Notes") or "").strip()

                dc, bonus = dc_bonus_from_score(score)

                # ✅ Upsert by (week, faction_id)
                sb.table("reputation").upsert({
                    "week": week,
                    "faction_id": faction_id,
                    "score": score,
                    "dc": dc,
                    "bonus": bonus,
                    "note": note,
                }).execute()

            st.success("Saved reputation updates to Supabase.")
            st.rerun()

        except Exception as e:
            st.error(f"Failed to save: {e}")
else:
    st.warning("DM locked. Players can view only.")
