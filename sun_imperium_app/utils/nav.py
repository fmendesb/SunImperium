import streamlit as st

def hide_default_sidebar_nav() -> None:
    """Hides Streamlit's built-in multipage sidebar navigation."""
    st.markdown(
        """
        <style>
            section[data-testid="stSidebarNav"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )
