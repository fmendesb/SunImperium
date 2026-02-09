import streamlit as st

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.nav import sidebar

# Always render the custom nav on the home page too.
sidebar(None)

st.title("🌙 Sun Imperium")
st.caption("Choose a section from the sidebar.")
