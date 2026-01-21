from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st

from utils.supabase_client import get_supabase
from utils import crafting as c


st.set_page_config(page_title="Crafting Hub", page_icon="🧰", layout="wide")

sb = get_supabase()

st.title("🧰 Crafting Hub")
st.caption("Gather, craft, track timers, and manage inventory. Persistent data lives in Supabase.")

# ----------------------------
# Player selector
# ----------------------------
players = c.list_players(sb)
if not players:
    st.warning("No players found in Supabase table `players`. Add players first.")
    st.stop()

name_to_id = {p["name"]: p["id"] for p in players}
player_name = st.sidebar.selectbox("Select Player", list(name_to_id.keys()))
player_id = name_to_id[player_name]

progress = c.get_player_progress(sb, player_id)
skills = progress.get("skills") or {}
professions = c.get_professions_from_skills(skills)

st.sidebar.subheader("Professions")
if professions:
    for prof in professions:
        lvl = c.get_skill_level(skills, prof)
        st.sidebar.write(f"- {prof}: Level {lvl} (T{c.unlocked_max_tier_for_skill(lvl)})")
else:
    st.sidebar.info("No professions set yet. You can edit `player_progress.skills` in Supabase.")

# ----------------------------
# Tabs
# ----------------------------
tab_inv, tab_gather, tab_craft, tab_jobs, tab_log, tab_undo = st.tabs(
    ["📦 Inventory", "⛏️ Gather", "🛠️ Craft", "⏳ Jobs", "📜 Log", "↩️ Undo"]
)

# ---------- Inventory ----------
with tab_inv:
    st.subheader(f"Inventory: {player_name}")
    inv_rows = c.list_inventory(sb, player_id)
    if not inv_rows:
        st.info("Inventory is empty.")
    else:
        st.dataframe(inv_rows, use_container_width=True, hide_index=True)

# ---------- Gather ----------
with tab_gather:
    st.subheader("Gather")
    if not professions:
        st.info("This player has no professions yet. Add professions in `player_progress.skills`.")
    else:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            g_prof = st.selectbox("Gathering Profession", professions, key="g_prof")
        with col2:
            lvl = c.get_skill_level(skills, g_prof)
            max_tier = c.unlocked_max_tier_for_skill(lvl)
            g_tier = st.selectbox("Max Tier", list(range(1, max_tier + 1)), index=max_tier - 1, key="g_tier")
        with col3:
            qty = st.number_input("Quantity", min_value=1, max_value=999, value=1, step=1, key="g_qty")

        items = c.list_gathering_items(sb, profession=g_prof, max_tier=int(g_tier))
        if not items:
            st.warning("No gathering items found for this profession/tier. Check `gathering_items` table.")
        else:
            item_names = [f"T{it['tier']} • {it['name']}" for it in items]
            pick = st.selectbox("Item", item_names, key="g_item_pick")
            chosen = items[item_names.index(pick)]

            st.markdown("**Details**")
            st.write(chosen.get("description") or "")
            st.caption(f"Region: {chosen.get('region','')} | Family: {chosen.get('family','')}")

            if st.button("Start Gather Job", type="primary"):
                try:
                    c.start_gather(sb, player_id=player_id, item=chosen, qty=int(qty))
                    st.success("Gather job started.")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

# ---------- Craft ----------
with tab_craft:
    st.subheader("Craft")
    if not professions:
        st.info("This player has no professions yet. Add professions in `player_progress.skills`.")
    else:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            craft_prof = st.selectbox("Crafting Profession", professions, key="craft_prof")
        with col2:
            lvl = c.get_skill_level(skills, craft_prof)
            max_tier = c.unlocked_max_tier_for_skill(lvl)
            craft_tier = st.selectbox("Max Tier", list(range(1, max_tier + 1)), index=max_tier - 1, key="craft_tier")
        with col3:
            craft_qty = st.number_input("Quantity", min_value=1, max_value=99, value=1, step=1, key="craft_qty")

        recipes = c.list_recipes(sb, profession=craft_prof, max_tier=int(craft_tier))
        if not recipes:
            st.warning("No recipes found for this profession/tier. Check `recipes` table.")
        else:
            recipe_names = [f"T{r['tier']} • {r['name']}" for r in recipes]
            pick = st.selectbox("Recipe", recipe_names, key="recipe_pick")
            recipe = recipes[recipe_names.index(pick)]

            st.markdown("**Recipe**")
            st.write(recipe.get("description") or "")
            comps = recipe.get("components") or []
            if isinstance(comps, str):
                try:
                    comps = json.loads(comps)
                except Exception:
                    comps = []

            inv_map = c.inventory_map(sb, player_id)
            ok, missing = c.can_craft(inv_map, comps, qty=int(craft_qty))

            st.markdown("**Components**")
            for comp in comps:
                n = comp.get("name")
                need = int(comp.get("qty") or 0) * int(craft_qty)
                have = int(inv_map.get(n, 0))
                st.write(f"- {n}: need {need}, have {have}")

            if not ok:
                st.warning("Missing components. You can't start this craft yet.")

            if st.button("Start Craft Job", type="primary", disabled=(not ok)):
                try:
                    c.start_craft(sb, player_id=player_id, recipe=recipe, qty=int(craft_qty))
                    st.success("Craft job started (components consumed).")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

# ---------- Jobs ----------
with tab_jobs:
    st.subheader("Jobs")
    jobs = c.list_jobs(sb, player_id, status=None)
    active = [j for j in jobs if j.get("status") == "active"]
    completed = [j for j in jobs if j.get("status") == "completed"]

    if not jobs:
        st.info("No jobs yet.")
    else:
        st.markdown("### Active")
        if not active:
            st.caption("No active jobs.")
        for j in active:
            started = datetime.fromisoformat(j["started_at"].replace("Z","+00:00"))
            completes = datetime.fromisoformat(j["completes_at"].replace("Z","+00:00"))
            now = datetime.now(timezone.utc)
            total = max(1, int(j.get("duration_seconds") or 1))
            elapsed = (now - started).total_seconds()
            pct = max(0.0, min(1.0, elapsed / total))
            label = j.get("item_name") or j.get("recipe_name") or "Job"
            st.write(f"**{j.get('kind','job').title()}**: {label}")
            st.progress(pct)
            if now >= completes:
                st.success("Ready to claim.")
                if st.button(f"Claim ({j['id']})", key=f"claim_{j['id']}"):
                    try:
                        c.claim_job_rewards(sb, player_id=player_id, job=j)
                        st.success("Claimed.")
                        st.rerun()
                    except Exception as e:
                        st.error(str(e))
            else:
                remaining = int((completes - now).total_seconds())
                st.caption(f"Time remaining: {remaining//60}m {remaining%60}s")

        st.markdown("### Completed")
        if not completed:
            st.caption("No completed jobs.")
        else:
            # show recent few
            for j in completed[:10]:
                label = j.get("item_name") or j.get("recipe_name") or "Job"
                st.write(f"✅ {j.get('kind','job').title()}: {label} (claimed)")

# ---------- Log ----------
with tab_log:
    st.subheader("Activity Log")
    rows = c.list_activity(sb, player_id, limit=50)
    if not rows:
        st.info("No activity yet.")
    else:
        st.dataframe(rows, use_container_width=True, hide_index=True)

# ---------- Undo ----------
with tab_undo:
    st.subheader("Undo")
    col1, col2 = st.columns([1, 2])
    with col1:
        category = st.selectbox("Category", ["gather", "craft"], index=0)
        if st.button("Undo Last Action", type="secondary"):
            try:
                ok = c.undo_last(sb, player_id=player_id, category=category)
                if not ok:
                    st.info("Nothing to undo in this category.")
                else:
                    st.success("Undone.")
                    st.rerun()
            except Exception as e:
                st.error(str(e))
    with col2:
        st.caption("Undo cancels the latest job in that category. Craft undo also refunds components (if they were consumed).")
