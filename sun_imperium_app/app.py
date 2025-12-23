import streamlit as st
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap

st.set_page_config(
    page_title="Sun Imperium | The Silver Council",
    page_icon="🌙",
    layout="wide",
)

st.title("🌙 The Silver Council")
st.caption("Aurelen Strategic Console · Moon Glade Resistance")

sb = get_supabase()
ensure_bootstrap(sb)

st.markdown(
    """
Welcome. Use the sidebar to navigate.

**Modules**
- **The Silver Council**: Dashboard, Reputation, Legislation, Diplomacy, Infrastructure
- **Moonblade Guild**: Military + War Simulator
- **Dawnbreakers**: Intelligence

"""
)
