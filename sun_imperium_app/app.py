import streamlit as st
from importlib import import_module

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide Streamlit's default multipage sidebar navigation (the auto-generated list from /pages).
st.markdown(
    """
    <style>
      /* cover multiple Streamlit versions */
      section[data-testid="stSidebarNav"] { display: none; }
      div[data-testid="stSidebarNav"] { display: none; }
      nav[data-testid="stSidebarNav"] { display: none; }
      [data-testid="stSidebarNav"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

PAGES = {
    "🏛 Dashboard": "sun_imperium_app.pages.01_Silver_Council_Dashboard",
    "🏗 Silver Council Shop": "sun_imperium_app.pages.02_Silver_Council_Infrastructure",
    "📜 Reputation": "sun_imperium_app.pages.03_Silver_Council_Reputation",
    "📖 Legislation": "sun_imperium_app.pages.04_Silver_Council_Legislation",
    "🤝 Diplomacy": "sun_imperium_app.pages.05_Silver_Council_Diplomacy",
    "🕵 Intelligence": "sun_imperium_app.pages.06_Dawnbreakers_Intelligence",
    "⚔ Military": "sun_imperium_app.pages.07_Moonblade_Guild_Military",
    "🩸 War Simulator": "sun_imperium_app.pages.08_War_Simulator",
    "🛠 Crafting Hub": "sun_imperium_app.pages.09_Crafting_Hub",
    "🧿 DM Console": "sun_imperium_app.pages.99_DM_Console",
}

st.sidebar.title("Sun Imperium")
choice = st.sidebar.radio("Navigation", list(PAGES.keys()), key="nav_choice")

mod = import_module(PAGES[choice])

if hasattr(mod, "render"):
    mod.render()
else:
    st.error(f"Page module {PAGES[choice]} has no render() function.")
