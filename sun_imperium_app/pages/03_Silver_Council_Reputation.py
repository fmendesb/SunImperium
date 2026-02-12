import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week

page_config("Reputation", "📜")
sidebar("📜 Reputation")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("📜 Reputation")
st.caption(f"Week {week}")

# Filters
filter_view = st.radio("Show", ["All", "Regions", "Families"], horizontal=True)

def dc_from_score(score: int) -> int:
    # Monotonic: higher score => lower DC
    s = max(0, min(10, int(score)))
    dc_table = {0: 20, 1: 19, 2: 18, 3: 17, 4: 16, 5: 15, 6: 14, 7: 13, 8: 12, 9: 11, 10: 10}
    return dc_table[s]

# Load all factions (reputation targets)
factions = (
    sb.table("factions")
    .select("id,name,type,is_hidden")
    .order("type")
    .order("name")
    .execute()
    .data
    or []
)

if filter_view == "Regions":
    factions = [f for f in factions if (f.get("type") or "").lower() == "region"]
elif filter_view == "Families":
    factions = [f for f in factions if (f.get("type") or "").lower() == "family"]

# Load current week reputation rows
rep_rows = (
    sb.table("reputation")
    .select("faction_id,score,dc,note")
    .eq("week", week)
    .execute()
    .data
    or []
)
rep_by_id = {r["faction_id"]: r for r in rep_rows if r.get("faction_id")}

rows = []
for f in factions:
    fid = f["id"]
    r = rep_by_id.get(fid, {})
    score = int(r.get("score") or 0)
    dc = int(r.get("dc") or dc_from_score(score))
    rows.append(
        {
            "Name": f.get("name") or "",
            "Type": f.get("type") or "",
            "Score": score,
            "DC": dc,
            "Note": r.get("note") or "",
            "_faction_id": fid,
        }
    )

df = pd.DataFrame(rows)
if df.empty:
    st.info("No reputations found.")
else:
    edited = st.data_editor(
        df.drop(columns=["_faction_id"]),
        use_container_width=True,
        hide_index=True,
        disabled=["Name", "Type"],
        key="rep_editor",
    )

    if dm_gate("DM password required to save reputation changes", key="rep_save_gate"):
        if st.button("Save changes", type="primary"):
            # Map back by name for edited rows
            name_to_fid = {r["Name"]: r["_faction_id"] for r in rows}
            for _, row in edited.iterrows():
                fid = name_to_fid.get(row["Name"])
                if not fid:
                    continue
                score = int(row["Score"] or 0)
                dc = dc_from_score(score)
                sb.table("reputation").upsert(
                    {
                        "week": week,
                        "faction_id": fid,
                        "score": score,
                        "dc": dc,
                        "note": (row.get("Note") or ""),
                    },
                    on_conflict="week,faction_id",
                ).execute()
            st.success("Saved.")
            st.rerun()
