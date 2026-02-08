import streamlit as st
from typing import Optional

def dm_gate(prompt: str, key: str = "dm", password: Optional[str] = None) -> bool:
    """
    DM gate that is safe to call inside or outside st.form().
    It does NOT use st.button(), avoiding StreamlitAPIException.
    Unlock persists in st.session_state for the given key.
    """
    expected = password or st.secrets.get("DM_PASSWORD") or st.session_state.get("DM_PASSWORD")

    if not expected:
        st.warning("DM password not configured (DM_PASSWORD).")
        return False

    unlocked_key = f"dm_unlocked_{key}"
    if st.session_state.get(unlocked_key):
        return True

    st.info(prompt)
    entered = st.text_input("DM Password", type="password", key=f"{key}_pwd")

    if entered and entered == expected:
        st.session_state[unlocked_key] = True
        return True

    return False
