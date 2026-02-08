import streamlit as st

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
)

# Multipage apps load app.py first. We want players to land on the Dashboard page.
# switch_page exists in modern Streamlit; if unavailable, we show a big link instead.
try:
    st.switch_page("pages/01_Silver_Council_Dashboard.py")
except Exception:
    st.title("🌙 Sun Imperium")
    st.write("Use the sidebar to navigate, or jump directly to the Dashboard.")
    try:
        st.page_link(
            "pages/01_Silver_Council_Dashboard.py",
            label="🏛️ Go to Dashboard",
        )
    except Exception:
        st.markdown("**Go to:** Silver Council → Dashboard")
