import streamlit as st

def hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in multipage navigation (file-based Pages list).

    Streamlit's DOM varies by version, so we target multiple selectors.
    """
    
    st.markdown(
    """
    <style>
      /* Hide Streamlit's built-in multipage navigation list */
      section[data-testid="stSidebarNav"] { display: none !important; }

      /* Force sidebar container visible (prevents 'disappearing') */
      section[data-testid="stSidebar"] { display: block !important; visibility: visible !important; }

      /* Ensure the sidebar content area is visible */
      [data-testid="stSidebarContent"] { display: block !important; visibility: visible !important; }

      /* If Streamlit collapses sidebar, keep it expanded */
      button[kind="header"] { visibility: visible !important; }
    </style>
    """,
    unsafe_allow_html=True,
    )

def page_config(title: str, icon: str = "🌙") -> None:
    """Backwards-compatible helper.

    IMPORTANT: Do not call st.set_page_config here (must be first Streamlit command).
    Also: do not render a page title here to avoid duplicate headers.
    Pages should render their own titles.
    """
    # Intentionally a no-op besides an optional tiny caption.
    st.caption(f"{icon} {title}")

def _load_hidden_pages() -> set[str]:
    """Best-effort load of ui_hidden_pages from app_state."""
    try:
        from utils.supabase_client import get_supabase  # local import to avoid hard dependency at module import
        sb = get_supabase()
        row = sb.table("app_state").select("id,ui_hidden_pages").eq("id", 1).limit(1).execute().data or []
        if row and isinstance(row[0].get("ui_hidden_pages"), list):
            return set(row[0].get("ui_hidden_pages") or [])
    except Exception:
        pass
    return set()

def sidebar(active: str | None = None) -> None:
    """Render the custom emoji navigation and hide the default nav."""
    hide_default_sidebar_nav()

    st.sidebar.markdown("## 🌙 Sun Imperium")
    st.sidebar.caption("Navigation")

    is_dm = bool(st.session_state.get("is_dm", False))
    hidden_pages = _load_hidden_pages() if not is_dm else set()

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
        fname = target.split("/")[-1]
        if (not is_dm) and (fname in hidden_pages):
            continue
        prefix = "➡️ " if (active and label == active) else ""
        st.sidebar.page_link(target, label=f"{prefix}{label}")
