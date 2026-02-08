import streamlit as st
from importlib import import_module

st.set_page_config(page_title="Sun Imperium", page_icon="🌙", layout="wide")

# Hide Streamlit default page nav
st.markdown(
    "<style>section[data-testid='stSidebarNav']{display:none;}</style>",
    unsafe_allow_html=True,
)

PAGES = {
    "🏛 Dashboard": "pages.01_Silver_Council_Dashboard",
    "🏗 Silver Council Shop": "pages.02_Silver_Council_Infrastructure",
    "📜 Reputation": "pages.03_Silver_Council_Reputation",
    "📖 Legislation": "pages.04_Silver_Council_Legislation",
    "🤝 Diplomacy": "pages.05_Silver_Council_Diplomacy",
    "🕵 Intelligence": "pages.06_Dawnbreakers_Intelligence",
    "⚔ Military": "pages.07_Moonblade_Guild_Military",
    "🩸 War Simulator": "pages.08_War_Simulator",
    "🛠 Crafting Hub": "pages.09_Crafting_Hub",
    "🧿 DM Console": "pages.99_DM_Console",
}

st.sidebar.title("Sun Imperium")
choice = st.sidebar.radio("Navigation", list(PAGES.keys()))

mod = import_module(PAGES[choice])

# Each page file must expose a render() function.
if hasattr(mod, "render"):
    mod.render()
else:
    st.error(f"{PAGES[choice]} has no render() function.")
