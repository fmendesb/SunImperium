import streamlit as st
import pandas as pd

from utils.nav import hide_default_sidebar_nav
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate

hide_default_sidebar_nav()

sb = get_supabase()
ensure_bootstrap(sb)

st.title("📖 Legislation")
st.caption("Codex of laws. DM can add or edit; players can read.")

# Display existing laws
try:
    rows = (
        sb.table("legislation")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
except Exception:
    rows = []

if rows:
    df = pd.DataFrame(rows)
    # Players don't need internal IDs/timestamps
    df = df.drop(columns=["id", "created_at", "updated_at"], errors="ignore")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No legislation yet.")

st.divider()

# DM section
unlocked = dm_gate("DM password required to edit legislation", key="leg")

with st.expander("DM: Add a law", expanded=False):
    title = st.text_input("Title", key="law_title")
    category = st.text_input("Category", key="law_category")
    text = st.text_area("Text", height=200, key="law_text")

    if st.button("Save", type="primary", key="law_save"):
        if not unlocked:
            st.error("DM password required.")
        else:
            payload = {"title": title, "category": category, "text": text}
            try:
                sb.table("legislation").insert(payload).execute()
                st.success("Law added.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save law: {e}")
