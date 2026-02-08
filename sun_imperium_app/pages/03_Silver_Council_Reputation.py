import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.nav import hide_default_sidebar_nav
from utils.ledger import get_current_week

st.set_page_config(page_title="Reputation", page_icon="📜", layout="wide")
hide_default_sidebar_nav()

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("📜 Reputation")
st.caption(f"Week {week} · Editing requires DM unlock.")

try:
    factions = sb.table("factions").select("id,name,type,is_hidden").order("type").order("name").execute().data or []
except Exception:
    factions = sb.table("factions").select("id,name,type").order("type").order("name").execute().data or []
    for f in factions:
        f["is_hidden"] = False

is_dm = bool(st.session_state.get("is_dm", False))
show_hidden = st.toggle("Show hidden (DM only)", value=False) if is_dm else False

filter_view = st.radio("Filter", ["All", "Regions", "Families"], horizontal=True)

def is_family(t: str) -> bool:
    return str(t) in {"family", "house"}

if filter_view == "Regions":
    factions = [f for f in factions if str(f.get("type")) == "region"]
elif filter_view == "Families":
    factions = [f for f in factions if is_family(f.get("type"))]

if not show_hidden:
    factions = [f for f in factions if not bool(f.get("is_hidden", False))]

rep_rows = sb.table("reputation").select("week,faction_id,score,dc,bonus,note").eq("week", week).execute().data or []
rep_map = {r["faction_id"]: r for r in rep_rows}

def dc_bonus_from_score(score: int):
    score = max(0, min(10, int(score)))
    dc = 20 - score
    bonus = score - 3
    return dc, bonus

rows = []
for f in factions:
    r = rep_map.get(f["id"], {})
    score = int(r.get("score") or 0)
    dc, bonus = dc_bonus_from_score(score)
    rows.append({
        "Faction": f.get("name"),
        "Type": f.get("type"),
        "Score": score,
        "DC": dc,
        "Bonus": bonus,
        "Notes": r.get("note") or "",
        "_faction_id": f["id"],
    })

df = pd.DataFrame(rows)
if df.empty:
    st.info("No reputations to display.")
    st.stop()

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

unlocked = dm_gate("DM password required to save reputation changes", key="rep")
if st.button("💾 Save changes", type="primary", disabled=not unlocked):
    try:
        for i, row in edited.iterrows():
            faction_id = df.iloc[i]["_faction_id"]
            score = int(row["Score"])
            dc, bonus = dc_bonus_from_score(score)
            sb.table("reputation").upsert(
                {
                    "week": week,
                    "faction_id": faction_id,
                    "score": score,
                    "dc": dc,
                    "bonus": bonus,
                    "note": str(row.get("Notes") or ""),
                },
                on_conflict="week,faction_id",
            ).execute()
        st.success("Saved to Supabase.")
        st.rerun()
    except Exception as e:
        st.error(f"Failed to save: {e}")
