import streamlit as st

from utils.nav import page_config, sidebar


# Main entrypoint: we keep this as a router to the Dashboard.
page_config("Sun Imperium", "🌙")
sidebar("🏛 Dashboard")

# Send users to the real dashboard page.
try:
    st.switch_page("pages/01_Silver_Council_Dashboard.py")
except Exception:
    st.title("Sun Imperium")
    st.write("Use the sidebar to open the Dashboard.")
