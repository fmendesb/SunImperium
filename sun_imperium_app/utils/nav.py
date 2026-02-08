import streamlit as st


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


def page_config(page_title: str, page_icon: str = "🌙") -> None:
    """Must be called before any other Streamlit command in a page."""
    st.set_page_config(page_title=page_title, page_icon=page_icon, layout="wide")
    hide_default_sidebar_nav()


def hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in multipage nav so only our emoji nav remains."""
    st.markdown(
        """
        <style>
          section[data-testid="stSidebarNav"],
          div[data-testid="stSidebarNav"],
          nav[data-testid="stSidebarNav"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar(current_label: str | None = None) -> None:
    """Render the emoji sidebar. Uses page_link if available (single click)."""
    st.sidebar.title("Sun Imperium")

    # Streamlit has page_link in modern versions; fall back to switch_page.
    page_link = getattr(st.sidebar, "page_link", None)

    if callable(page_link):
        for label, path in PAGES:
            # Highlighting is handled by Streamlit; we keep it simple.
            page_link(path, label=label)
    else:
        # Fallback: radio + switch_page (may take 2 clicks on some cached UIs)
        labels = [lbl for lbl, _ in PAGES]
        idx = labels.index(current_label) if current_label in labels else 0
        choice = st.sidebar.radio("Navigation", labels, index=idx)
        target = dict(PAGES)[choice]
        if st.session_state.get("_nav_last") != choice:
            st.session_state["_nav_last"] = choice
            st.switch_page(target)
