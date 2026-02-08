import streamlit as st

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 🔥 THIS HIDES STREAMLIT'S DEFAULT PAGE NAV
st.markdown(
    """
    <style>
        section[data-testid="stSidebarNav"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Route to the dashboard (multipage apps open app.py by default).
try:
    st.switch_page("pages/01_Silver_Council_Dashboard.py")
except Exception:
    st.title("🏛️ Sun Imperium")
    st.write("Open the Dashboard page from the sidebar.")
