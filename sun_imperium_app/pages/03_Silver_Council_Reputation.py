import streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.ledger import get_current_week


st.set_page_config(page_title="Silver Council | Reputation", page_icon="📜", layout="wide")


def dc_bonus_from_score(score: int) -> tuple[int, int]:
    """Monotonic mapping: higher rep => lower DC, higher bonus.

    Replace this with your canon table if it differs.
    This fixes the bug where different scores produced identical DCs.
    """
    s = int(score)
    s = max(0, min(10, s))
    dc = 20 - s  # 0->20 ... 10->10
    bonus = -3 + s  # 0->-3 ... 10->+7
    return dc, bonus


sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

st.title("📜 Reputation")
st.caption(f"Week {week}")

is_dm = bool(st.session_state.get("is_dm", False))

# Filters
colf1, colf2, colf3 = st.columns([1, 1, 2])
with colf1:
    view = st.radio("Filter", ["All", "Regions", "Families"], horizontal=True)
with colf2:
    show_hidden = False
    if is_dm:
        show_hidden = st.toggle("Show hidden (DM)", value=False)
with colf3:
    st.write("")

# Load factions (these define the available reputations)
# We filter visibility via factions.is_hidden (DM can override).
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
    # if is_hidden doesn't exist yet, fall back
    factions = (
        sb.table("factions")
        .select("id,name,type")
        .order("type")
        .order("name")
        .execute()
        .data
        or []
    )
    for f in factions:
        f["is_hidden"] = False

if view == "Regions":
    factions = [f for f in factions if str(f.get("type")) == "region"]
elif view == "Families":
    factions = [f for f in factions if str(f.get("type")) in {"family", "house"}]

if not show_hidden:
    factions = [f for f in factions if not bool(f.get("is_hidden", False))]

# Load week reputation rows
rep_rows = (
    sb.table("reputation")
    .select("week,faction_id,score,dc,bonus,note")
    .eq("week", week)
    .execute()
    .data
    or []
)
rep_by_faction = {r["faction_id"]: r for r in rep_rows}

# Build UI table
rows = []
for f in factions:
    r = rep_by_faction.get(f["id"], {})
    score = int(r.get("score") or 0)
    dc, bonus = dc_bonus_from_score(score)
    rows.append(
        {
            "Name": f.get("name", ""),
            "Type": f.get("type", ""),
            "Score": score,
            "DC": dc,
            "Bonus": bonus,
            "Notes": r.get("note") or "",
            "_faction_id": f["id"],
            "_faction_type": str(f.get("type") or ""),
        }
    )

df = pd.DataFrame(rows)
if df.empty:
    st.info("No reputations to show with these filters.")
    st.stop()

edited = st.data_editor(
    df.drop(columns=["_faction_id", "_faction_type"]),
    use_container_width=True,
    hide_index=True,
    column_config={
        "Name": st.column_config.TextColumn(disabled=True),
        "Type": st.column_config.TextColumn(disabled=True),
        "DC": st.column_config.NumberColumn(disabled=True),
        "Bonus": st.column_config.NumberColumn(disabled=True),
    },
)

st.caption("DM changes persist to Supabase. DC/Bonus are auto-derived from Score.")

if dm_gate("DM password required to save reputation changes", key="rep_save_gate"):
    if st.button("💾 Save changes", type="primary"):
        try:
            for i, row in edited.iterrows():
                faction_id = df.iloc[i]["_faction_id"]
                faction_type = df.iloc[i]["_faction_type"]
                score = int(row["Score"])
                note = str(row.get("Notes") or "").strip()
                dc, bonus = dc_bonus_from_score(score)

                payload = {
                    "week": week,
                    "faction_id": faction_id,
                    "score": score,
                    "dc": dc,
                    "bonus": bonus,
                    "note": note,
                }

                # IMPORTANT: upsert by (week, faction_id) to avoid duplicate key errors
                sb.table("reputation").upsert(payload, on_conflict="week,faction_id").execute()

                # Best-effort: also write to region_week_state / family_week_state so economy reacts.
                # If those tables/columns don't exist, we ignore rather than break the page.
                try:
                    if faction_type == "region":
                        sb.table("region_week_state").upsert(
                            {"week": week, "region": row["Name"], "reputation_score": score},
                            on_conflict="week,region",
                        ).execute()
                    elif faction_type in {"family", "house"}:
                        sb.table("family_week_state").upsert(
                            {"week": week, "family": row["Name"], "reputation_score": score},
                            on_conflict="week,family",
                        ).execute()
                except Exception:
                    pass

            st.success("Reputation updated.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save: {e}")
else:
    st.info("View-only (DM locked).")

