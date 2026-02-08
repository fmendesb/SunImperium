import streamlit as st

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.nav import sidebar, hide_default_sidebar_nav

# Ensure the custom navigation is visible immediately on the home page too.
hide_default_sidebar_nav()
sidebar()

st.title("Sun Imperium")
st.caption("Select a page from the navigation.")

st.info(
    "If you ever see a 'Failed to fetch dynamically imported module' error after deploying, "
    "open the app in an incognito window or hard refresh (Ctrl+F5 / Cmd+Shift+R). "
    "That's a Streamlit Cloud browser cache mismatch, not a server-side bug."
)
