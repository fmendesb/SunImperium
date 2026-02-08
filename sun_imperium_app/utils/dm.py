import streamlit as st


def dm_gate(prompt: str, key: str = "dm", password: str | None = None) -> bool:
    """Password gate that is safe inside st.form (no buttons).

    - Stores unlocked state in session_state.
    - Sets st.session_state['is_dm']=True when unlocked so the router can show DM-only pages.
    """
    expected = password or st.secrets.get("DM_PASSWORD") or st.session_state.get("DM_PASSWORD")

    if not expected:
        st.warning("DM password not configured (DM_PASSWORD).")
        return False

    unlocked_key = f"dm_unlocked_{key}"
    if st.session_state.get(unlocked_key):
        st.session_state["is_dm"] = True
        return True

    st.info(prompt)
    entered = st.text_input("DM Password", type="password", key=f"{key}_pwd")

    if entered and entered == expected:
        st.session_state[unlocked_key] = True
        st.session_state["is_dm"] = True
        st.success("Unlocked.")
        return True

    return False
