import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.dm import dm_gate
from utils.nav import hide_default_sidebar_nav

st.set_page_config(page_title="Legislation", page_icon="📖", layout="wide")
hide_default_sidebar_nav()

sb = get_supabase()
ensure_bootstrap(sb)

st.title("📖 Legislation")
st.caption("Codex of laws and decrees (player-visible). Editing requires DM unlock.")

# Load current lawsimport streamlit as st
import pandas as pd

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.undo import log_action, get_last_action, pop_last_action


def render():
    UNDO_CATEGORY = "legislation"


    sb = get_supabase()
    ensure_bootstrap(sb)

    st.title("📜 Legislation")
    st.caption("The Silver Council Codex")

    with st.popover("↩️ Undo (Legislation)"):
        last = get_last_action(sb, category=UNDO_CATEGORY)
        if not last:
            st.write("No actions to undo.")
        else:
            payload = last.get("payload") or {}
            st.write(f"Last: {last.get('action','')} · {payload.get('title','')}")
            if st.button("Undo last", key="undo_leg"):
                if last.get("action") == "add_law" and payload.get("law_id"):
                    sb.table("legislation").delete().eq("id", payload["law_id"]).execute()
                    pop_last_action(sb, action_id=last["id"])
                    st.success("Undone.")
                    st.rerun()
                else:
                    st.error("Undo not implemented for this action type.")

    rows = sb.table("legislation").select("id,chapter,item,article,title,dc,description,effects,active").order("chapter").order("item").order("article").execute().data

    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["chapter","item","article","title","dc","active"])

    # Hide internal columns from players
    df = df.drop(columns=["id", "created_at"], errors="ignore")

    st.subheader("Codex")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Add / Update Law")
    with st.form("law_form", clear_on_submit=False):
        c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
        with c1:
            chapter = st.text_input("Chapter", value="")
        with c2:
            item = st.text_input("Item", value="")
        with c3:
            article = st.text_input("Article", value="")
        with c4:
            title = st.text_input("Title", value="")

        dc = st.number_input("DC", min_value=0, max_value=50, value=0, step=1)
        description = st.text_area("Description", value="")
        effects = st.text_area("Effects (free text for now)", value="")
        active = st.checkbox("Active", value=True)

        submitted = st.form_submit_button("Save")
        if submitted:
            ins = (
                sb.table("legislation")
                .insert(
                    {
                        "chapter": chapter,
                        "item": item,
                        "article": article,
                        "title": title,
                        "dc": int(dc),
                        "description": description,
                        "effects": effects,
                        "active": active,
                    }
                )
                .execute()
            )
            law_id = ins.data[0]["id"] if ins.data else None
            log_action(sb, category=UNDO_CATEGORY, action="add_law", payload={"law_id": law_id, "title": title})
            st.success("Saved.")
            st.rerun()
laws = []
try:
    laws = (
        sb.table("legislation")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
except Exception as e:
    st.error(f"Could not load legislation: {e}")

if laws:
    df = pd.DataFrame(laws)
    df = df.drop(columns=["id"], errors="ignore")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No legislation recorded yet.")

st.divider()
st.subheader("Add Law")

unlocked = dm_gate("DM password required to edit legislation", key="leg")

with st.form("legislation_form"):
    title = st.text_input("Title", placeholder="e.g., The Moonvault Tax Edict")
    category = st.text_input("Category", placeholder="e.g., Economy / War / Diplomacy")
    text = st.text_area("Text", height=200, placeholder="Write the law here…")
    submitted = st.form_submit_button("Save")

if submitted:
    if not unlocked:
        st.error("DM password required to save legislation.")
    else:
        if not title.strip():
            st.error("Title is required.")
        else:
            payload = {
                "title": title.strip(),
                "category": (category or "").strip(),
                "text": (text or "").strip(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                sb.table("legislation").insert(payload).execute()
                st.success("Legislation saved.")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")
