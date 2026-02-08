import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.nav import hide_default_sidebar_nav

st.set_page_config(page_title="Legislation", page_icon="📖", layout="wide")
hide_default_sidebar_nav()

sb = get_supabase()
ensure_bootstrap(sb)

st.title("📖 Legislation")
st.caption("Codex of laws and decrees (player-visible). Editing requires DM unlock.")

# Load current laws
laws = []
try:
    laws = (
        sb.table("legislation")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
except Exception as e:
    st.error(f"Could not load legislation: {e}")

if laws:
    df = pd.DataFrame(laws)
    df = df.drop(columns=["id"], errors="ignore")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No legislation recorded yet.")

st.divider()
st.subheader("Add Law")

unlocked = dm_gate("DM password required to edit legislation", key="leg")

with st.form("legislation_form"):
    title = st.text_input("Title", placeholder="e.g., The Moonvault Tax Edict")
    category = st.text_input("Category", placeholder="e.g., Economy / War / Diplomacy")
    text = st.text_area("Text", height=200, placeholder="Write the law here…")
    submitted = st.form_submit_button("Save")

if submitted:
    if not unlocked:
        st.error("DM password required to save legislation.")
    else:
        if not title.strip():
            st.error("Title is required.")
        else:
            payload = {
                "title": title.strip(),
                "category": (category or "").strip(),
                "text": (text or "").strip(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                sb.table("legislation").insert(payload).execute()
                st.success("Legislation saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
