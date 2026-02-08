import streamlit as st


def hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in Pages navigation list (top list in sidebar)."""
    st.markdown(
        """
        <style>
          /* Hide built-in multipage nav (Streamlit versions vary in DOM) */
          section[data-testid='stSidebarNav'],
          div[data-testid='stSidebarNav'],
          nav[aria-label='App pages'],
          div[aria-label='App pages'] {
            display: none !important;
            height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
            overflow: hidden !important;
          }

          /* Keep sidebar visible */
          section[data-testid='stSidebar'],
          [data-testid='stSidebarContent'] {
            display: block !important;
            visibility: visible !important;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_config(title: str, icon: str = "🌙") -> None:
    """Lightweight page header helper (does NOT call st.set_page_config)."""
    st.markdown(f"# {icon} {title}")


def sidebar(active: str | None = None) -> None:
    """Render custom emoji nav and hide Streamlit's default nav."""
    hide_default_sidebar_nav()

    st.sidebar.markdown("## 🌙 Sun Imperium")
    st.sidebar.caption("Navigation")

    pages = [
        ("🏛 Dashboard", "pages/01_Silver_Council_Dashboard.py"),
        ("🏗 Shop", "pages/02_Silver_Council_Infrastructure.py"),
        ("📜 Reputation", "pages/03_Silver_Council_Reputation.py"),
        ("📖 Legislation", "pages/04_Silver_Council_Legislation.py"),
        ("🤝 Diplomacy", "pages/05_Silver_Council_Diplomacy.py"),
        ("🕵 Intelligence", "pages/06_Dawnbreakers_Intelligence.py"),
        ("⚔ Military", "pages/07_Moonblade_Guild_Military.py"),
        ("🩸 War Simulator", "pages/08_War_Simulator.py"),
        ("🛠 Crafting Hub", "pages/09_Crafting_Hub.py"),
        ("🧿 DM Console", "pages/99_DM_Console.py"),
    ]

    for label, target in pages:
        prefix = "➡️ " if (active and label == active) else ""
        st.sidebar.page_link(target, label=f"{prefix}{label}")
