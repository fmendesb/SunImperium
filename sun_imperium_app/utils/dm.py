import streamlit as st


def dm_gate(label: str = "DM action", key: str = "dm_gate") -> bool:
    """Shared password gate for DM-only actions.

    - Safe to call inside or outside st.form() (no st.button() usage).
    - Persists unlock state in st.session_state for this key.
    """
    dm_password = st.secrets.get("DM_PASSWORD", "") or st.session_state.get("DM_PASSWORD", "")

    # If no password configured, default to allow (dev-friendly).
    if not dm_password:
        return True

    ok_key = f"{key}_ok"
    if st.session_state.get(ok_key, False):
        st.success("DM unlocked.")
        return True

    st.info(f"🔒 {label}")
    entered = st.text_input("DM password", type="password", key=f"{key}_pwd")

    if entered and entered == dm_password:
        st.session_state[ok_key] = True
        st.success("Unlocked for this session.")
        return True

    return False
