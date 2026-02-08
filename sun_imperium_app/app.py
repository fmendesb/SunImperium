import streamlit as st

st.set_page_config(
    page_title="Sun Imperium",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

from utils.nav import hide_default_sidebar_nav

# Hide Streamlit's default multipage nav so only our emoji menu appears
hide_default_sidebar_nav()

st.sidebar.title("Sun Imperium")

# If you want DM-only hiding of pages, DM Console will set st.session_state['is_dm']=True when unlocked.
is_dm = bool(st.session_state.get("is_dm", False))

# Optional hidden pages list (best-effort; if table/column doesn't exist, we ignore)
hidden_pages = set()
try:
    from utils.supabase_client import get_supabase

    sb = get_supabase()
    app_state = sb.table("app_state").select("id,ui_hidden_pages").eq("id", 1).limit(1).execute().data or []
    if app_state and isinstance(app_state[0].get("ui_hidden_pages"), list):
        hidden_pages = set(app_state[0].get("ui_hidden_pages") or [])
except Exception:
    hidden_pages = set()

# Page links
PAGES = [
    ("🏛 Dashboard", "pages/01_Silver_Council_Dashboard.py"),
    ("🏗 Silver Council Shop", "pages/02_Silver_Council_Infrastructure.py"),
    ("📜 Reputation", "pages/03_Silver_Council_Reputation.py"),
    ("📖 Legislation", "pages/04_Silver_Council_Legislation.py"),
    ("🤝 Diplomacy", "pages/05_Silver_Council_Diplomacy.py"),
    ("🕵 Intelligence", "pages/06_Dawnbreakers_Intelligence.py"),
    ("⚔ Military", "pages/07_Moonblade_Guild_Military.py"),
    ("🩸 War Simulator", "pages/08_War_Simulator.py"),
    ("🛠 Crafting Hub", "pages/09_Crafting_Hub.py"),
    ("🧿 DM Console", "pages/99_DM_Console.py"),
]

# Render custom nav links.
# We use page_link so navigation is single-click and managed by Streamlit (no switch_page hacks).
for label, path in PAGES:
    fname = path.split("/")[-1]
    if (not is_dm) and fname in hidden_pages:
        continue

    try:
        st.sidebar.page_link(path, label=label)
    except Exception:
        # Fallback: show as plain text if page_link isn't available
        st.sidebar.write(label)

st.title("Sun Imperium")
st.caption("Select a page from the sidebar.")
