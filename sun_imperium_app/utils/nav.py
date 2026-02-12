import streamlit as st


def hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in multipage navigation list.

    Streamlit's DOM varies across versions, so we use multiple selectors.
    IMPORTANT: We only hide the *nav list*, never the sidebar container.
    """

    st.markdown(
        """
        <style>
          /* Built-in multipage nav list (varies by Streamlit version) */
          section[data-testid="stSidebarNav"] { display: none !important; }
          div[data-testid="stSidebarNav"] { display: none !important; }
          nav[aria-label="App pages"] { display: none !important; }
          [data-testid="stSidebarNavItems"] { display: none !important; }

          /* Keep sidebar container + content visible */
          section[data-testid="stSidebar"] { display: block !important; visibility: visible !important; }
          [data-testid="stSidebarContent"] { display: block !important; visibility: visible !important; }
          button[data-testid="collapsedControl"] { display: block !important; visibility: visible !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def page_config(_title: str, _icon: str = "🌙") -> None:
    """Backwards-compatible no-op.

    Historically pages called page_config() to show a header.
    Pages now render their own titles, so this must not print anything
    (prevents double titles) and MUST NOT call st.set_page_config().
    """

    return


def sidebar(active: str | None = None) -> None:
    """Render the custom emoji navigation everywhere."""

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

    # Rescue rope
    try:
        st.sidebar.page_link("app.py", label="🏠 Home")
        st.sidebar.divider()
    except Exception:
        pass

    for label, target in pages:
        prefix = "➡️ " if (active and label == active) else ""
        try:
            st.sidebar.page_link(target, label=f"{prefix}{label}")
        except Exception:
            st.sidebar.write(f"{prefix}{label}")
