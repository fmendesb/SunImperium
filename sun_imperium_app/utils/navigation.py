from __future__ import annotations

import streamlit as st
from supabase import Client


# Page registry (key -> (label, page_path))
PAGES = [
    ("dashboard", "🏛️ Dashboard", "app.py"),
    ("infra", "🏪 Silver Council Shop", "pages/02_Silver_Council_Infrastructure.py"),
    ("rep", "🗳️ Reputation", "pages/03_Silver_Council_Reputation.py"),
    ("laws", "📜 Legislation", "pages/04_Silver_Council_Legislation.py"),
    ("diplo", "🤝 Diplomacy", "pages/05_Silver_Council_Diplomacy.py"),
    ("intel", "🕵️ Intelligence", "pages/06_Dawnbreakers_Intelligence.py"),
    ("mil", "⚔️ Military", "pages/07_Moonblade_Guild_Military.py"),
    ("war", "🩸 War Simulator", "pages/08_War_Simulator.py"),
    ("craft", "🛠️ Crafting Hub", "pages/09_Crafting_Hub.py"),
    ("dm", "🧿 DM Console", "pages/99_DM_Console.py"),
]


def _get_hidden_keys(sb: Client) -> set[str]:
    try:
        row = sb.table("app_state").select("ui_hidden_pages").eq("id", 1).limit(1).execute().data
        if not row:
            return set()
        keys = row[0].get("ui_hidden_pages") or []
        if isinstance(keys, list):
            return {str(k) for k in keys}
        return set()
    except Exception:
        return set()


def inject_hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in multipage navigation."""
    st.markdown(
        """
        <style>
          [data-testid="stSidebarNav"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_nav(sb: Client, *, allow_dm_always: bool = True) -> None:
    """Render a DM-controllable navigation sidebar.

    Hidden pages are removed for all users; DM Console can unhide itself.
    """
    inject_hide_default_sidebar_nav()

    hidden = _get_hidden_keys(sb)

    st.sidebar.markdown("## Sun Imperium")
    for key, label, path in PAGES:
        if key in hidden and not (allow_dm_always and key == "dm"):
            continue
        st.sidebar.page_link(path, label=label)
