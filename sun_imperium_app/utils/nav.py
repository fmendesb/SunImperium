import streamlit as st

def hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in multipage navigation (the file-based Pages list)."""
    st.markdown(
        """
        <style>
          /* Hide Streamlit's built-in multipage navigation */
          section[data-testid="stSidebarNav"] { display: none !important; }
          /* Keep the sidebar itself visible */
          section[data-testid="stSidebar"] { display: block; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def page_config(title: str, icon: str = "🌙") -> None:
    """
    Backwards-compatible helper.

    IMPORTANT:
    - Do NOT call st.set_page_config() here. Streamlit requires it to be the first command
      in a script, and calling it from imported helpers causes intermittent crashes.
    - Pages can call this to standardize headings.
    """
    st.title(f"{icon} {title}")

def sidebar(active: str | None = None) -> None:
    """Render the custom emoji navigation and hide the default nav."""
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
