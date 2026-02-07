import streamlit as st

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.navigation import sidebar_nav


st.set_page_config(page_title="Silver Council | Dashboard", page_icon="🏛️", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
sidebar_nav(sb)

st.title("🏛️ Dashboard")
st.info(
    "This page is kept for backward compatibility. The dashboard now lives on the app home (app.py)."
)

if st.button("Go to Dashboard"):
    st.switch_page("app.py")

st.stop()
