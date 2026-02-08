import streamlit as st


def hide_default_sidebar_nav() -> None:
    """Hide Streamlit's built-in multipage navigation so only the emoji nav shows."""
    st.markdown(
        """
        <style>
          section[data-testid="stSidebarNav"] { display: none !important; }
          div[data-testid="stSidebarNav"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )
