import streamlit as st
from pathlib import Path
import importlib.util

# ---- App config (MUST be the first Streamlit command) ----
st.set_page_config(page_title="Sun Imperium", page_icon="🌙", layout="wide", initial_sidebar_state="expanded")

# Hide Streamlit's default multipage navigation (the file-based sidebar)
st.markdown(
    """
    <style>
      /* Newer Streamlit */
      section[data-testid="stSidebarNav"] { display: none !important; }
      /* Older/alternate containers */
      [data-testid="stSidebarNav"] { display: none !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

PAGES = {
    "🏛 Dashboard": "01_Silver_Council_Dashboard.py",
    "🏗 Silver Council Shop": "02_Silver_Council_Infrastructure.py",
    "📜 Reputation": "03_Silver_Council_Reputation.py",
    "📖 Legislation": "04_Silver_Council_Legislation.py",
    "🤝 Diplomacy": "05_Silver_Council_Diplomacy.py",
    "🕵 Intelligence": "06_Dawnbreakers_Intelligence.py",
    "⚔ Military": "07_Moonblade_Guild_Military.py",
    "🩸 War Simulator": "08_War_Simulator.py",
    "🛠 Crafting Hub": "09_Crafting_Hub.py",
    "🧿 DM Console": "99_DM_Console.py",
}

st.sidebar.title("Sun Imperium")
if "nav_choice" not in st.session_state:
    st.session_state["nav_choice"] = "🏛 Dashboard"

choice = st.sidebar.radio("Navigation", list(PAGES.keys()), index=list(PAGES.keys()).index(st.session_state["nav_choice"]))
st.session_state["nav_choice"] = choice

pages_dir = Path(__file__).resolve().parent / "pages"
target = pages_dir / PAGES[choice]

if not target.exists():
    st.error("Page file not found:")
    st.code(str(target))
    st.stop()

# Load a page module from a filepath (avoids Python package/module-name issues with Streamlit's /pages folder)
module_name = f"sunimp_page_{target.stem}"
spec = importlib.util.spec_from_file_location(module_name, target)
if spec is None or spec.loader is None:
    st.error("Could not load page module.")
    st.code(str(target))
    st.stop()

mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)  # type: ignore[attr-defined]

if hasattr(mod, "render") and callable(mod.render):
    mod.render()
else:
    st.error(f"{target.name} has no render() function.")
    st.info("Each page in /pages must define: def render(): ...")
