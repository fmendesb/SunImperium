import streamlit as st

def hide_streamlit_pages_nav_only() -> None:
    """
    Hide Streamlit's built-in multipage nav (the 'app / Silver Council…' list)
    WITHOUT hiding the sidebar itself.
    """
    st.markdown(
        """
        <style>
          /* Hide Streamlit multipage navigation list (different versions use different containers) */
          section[data-testid="stSidebarNav"] { display: none !important; }
          nav[aria-label="App pages"] { display: none !important; }
          div[data-testid="stSidebarNav"] { display: none !important; }

          /* Force the sidebar container + content to remain visible */
          section[data-testid="stSidebar"] { display: block !important; visibility: visible !important; width: var(--sidebar-width) !important; }
          [data-testid="stSidebarContent"] { display: block !important; visibility: visible !important; }

          /* Make sure the collapse button still exists */
          button[data-testid="collapsedControl"] { display: block !important; visibility: visible !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )

def sidebar(active: str | None = None) -> None:
    hide_streamlit_pages_nav_only()

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

    # “Rescue rope” in case Streamlit collapses the sidebar UI
    st.sidebar.page_link("app.py", label="🏠 Home (Navigation)")

    st.sidebar.divider()

    for label, target in pages:
        prefix = "➡️ " if (active and label == active) else ""
        st.sidebar.page_link(target, label=f"{prefix}{label}")
