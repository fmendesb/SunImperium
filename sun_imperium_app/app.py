import streamlit as st

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide Streamlit's default multipage navigation
st.markdown(
    """
    <style>
        section[data-testid="stSidebarNav"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

PAGES = {
    "🏛 Dashboard": "pages/01_Silver_Council_Dashboard.py",
    "🏗 Silver Council Shop": "pages/02_Silver_Council_Infrastructure.py",
    "📜 Reputation": "pages/03_Silver_Council_Reputation.py",
    "📖 Legislation": "pages/04_Silver_Council_Legislation.py",
    "🤝 Diplomacy": "pages/05_Silver_Council_Diplomacy.py",
    "🕵 Intelligence": "pages/06_Dawnbreakers_Intelligence.py",
    "⚔ Military": "pages/07_Moonblade_Guild_Military.py",
    "🩸 War Simulator": "pages/08_War_Simulator.py",
    "🛠 Crafting Hub": "pages/09_Crafting_Hub.py",
    "🧿 DM Console": "pages/99_DM_Console.py",
}

# Keep selection stable across refresh
if "nav_choice" not in st.session_state:
    st.session_state["nav_choice"] = "🏛 Dashboard"

st.sidebar.title("Sun Imperium")
choice = st.sidebar.radio(
    "Navigation",
    options=list(PAGES.keys()),
    index=list(PAGES.keys()).index(st.session_state["nav_choice"]),
)

st.session_state["nav_choice"] = choice

# Route
try:
    st.switch_page(PAGES[choice])
except Exception:
    st.title("Sun Imperium")
    st.error("Could not switch pages. Check that the target page file exists.")
    st.code(PAGES[choice])
