import streamlit as st


def dm_gate(label: str = "DM action", key: str = "dm_gate") -> bool:
    """Simple shared password gate for dangerous actions.

    Returns True if gate is open for the current session.
    """
    dm_password = st.secrets.get("DM_PASSWORD", "")
    if not dm_password:
        # If no password is configured, default to allow.
        return True

    if st.session_state.get(f"{key}_ok", False):
        return True

    with st.popover(f"🔒 {label}"):
        pwd = st.text_input("DM password", type="password", key=f"{key}_pwd")
        if st.button("Unlock", key=f"{key}_btn"):
            if pwd == dm_password:
                st.session_state[f"{key}_ok"] = True
                st.success("Unlocked for this session.")
            else:
                st.error("Wrong password.")

    return st.session_state.get(f"{key}_ok", False)
