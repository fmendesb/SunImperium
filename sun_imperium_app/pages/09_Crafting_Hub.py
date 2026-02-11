import streamlit as st
from datetime import datetime, timezone

from utils.nav import page_config, sidebar

from utils.supabase_client import get_supabase
import utils.crafting as crafting

page_config("Crafting Hub", "🧰")
sidebar("🛠 Crafting Hub")
st.title("🧰 Crafting Hub")

sb = get_supabase()
week = crafting.get_current_week(sb)

players = crafting.list_players(sb)
if not players:
    st.warning("No players found in Supabase table `players`.")
    st.stop()

player_name = st.sidebar.selectbox("Select Player", [p["name"] for p in players], index=0)
player = next(p for p in players if p["name"] == player_name)
player_id = player["id"]

progress = crafting.ensure_player_progress(sb, player_id)
professions = crafting.list_professions_for_player(progress)

# -------------------------
# Header: Skills + XP bars
# -------------------------
st.subheader("🧠 Skills & XP")

if not professions:
    st.info("This player has no professions yet (player_progress.skills is empty).")
else:
    for prof in professions:
        skill = (progress.get("skills") or {}).get(prof) or {"level": 1, "xp": 0}
        level = int(skill.get("level", 1))
        xp = int(skill.get("xp", 0))

        unlocked_tier = crafting.max_tier_for_level(sb, level)
        visible_cap = unlocked_tier + 2

        xp_this = crafting.xp_required_for_level(sb, level)
        xp_next = crafting.xp_required_for_level(sb, min(20, level + 1))
        denom = max(1, xp_next - xp_this)
        pct = max(0.0, min(1.0, (xp - xp_this) / denom))

        c1, c2, c3 = st.columns([0.42, 0.38, 0.20])
        with c1:
            st.markdown(f"**{prof}**")
            st.caption(f"Level {level} • Unlocked Tier T{unlocked_tier} • Visible up to T{visible_cap}")
        with c2:
            st.progress(pct)
            st.caption(f"XP {xp} • next level at {xp_next}")
        with c3:
            if st.button("➖ XP", key=f"xp_minus_{prof}"):
                crafting.set_skill_xp_delta(sb, player_id, prof, -1)
                st.rerun()
            if st.button("➕ XP", key=f"xp_plus_{prof}"):
                crafting.set_skill_xp_delta(sb, player_id, prof, +1)
                st.rerun()

with st.expander("📜 Activity Log", expanded=False):
    logs = crafting.get_activity_log(sb, player_id, limit=30)
    if not logs:
        st.caption("No activity yet.")
    else:
        for row in logs:
            st.write(f"• {row.get('message','')}")
            if row.get("created_at"):
                st.caption(str(row["created_at"]))

st.divider()

tab_inventory, tab_gather, tab_discovery, tab_craft, tab_vendor, tab_jobs = st.tabs(
    ["Inventory", "Gather", "Recipes (Discovery)", "Craft", "Vendor", "Jobs"]
)

# -------------------------
# Inventory (no 0 rows) + clean send section
# -------------------------
with tab_inventory:
    st.subheader("🎒 Inventory")

inv_rows = crafting.list_inventory(sb, player_id=player_id)

if not inv_rows:
    st.info("Your inventory is empty.")
else:
    # Build editable table
    base = [{"Item": r["item_name"], "Qty": int(r.get("qty") or r.get("quantity") or 0)} for r in inv_rows]
    df0 = pd.DataFrame(base)
    st.caption("Edit quantities and click Save (useful for DM adjustments/testing).")

    edited = st.data_editor(
        df0,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Item": st.column_config.TextColumn(disabled=True),
            "Qty": st.column_config.NumberColumn(min_value=0, step=1),
        },
        key="inv_editor",
    )

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("Save inventory", type="primary"):
            # Apply deltas
            orig = {r["item_name"]: int(r.get("qty") or r.get("quantity") or 0) for r in inv_rows}
            for _, row in edited.iterrows():
                name = row["Item"]
                new_qty = int(row["Qty"] or 0)
                delta = new_qty - int(orig.get(name, 0))
                if delta:
                    crafting.inventory_adjust(sb, player_id=player_id, item_name=name, delta=delta)
            st.success("Saved.")
            st.rerun()
    with c2:
        st.caption("Sending items uses the controls below.")

    st.markdown("#### Send items")
    recipients = sb.table("players").select("id,name").order("name").execute().data or []
    rec_map = {r["name"]: r["id"] for r in recipients if r.get("id") and r.get("name")}
    if rec_map:
        pick_item = st.selectbox("Item", list(df0["Item"]))
        pick_rec = st.selectbox("Recipient", list(rec_map.keys()))
        max_send = int(orig.get(pick_item, 0))
        send_qty = st.number_input("Amount", min_value=1, max_value=max_send if max_send > 0 else 1, value=1)
        if st.button("Send"):
            if max_send <= 0:
                st.error("You don't have any of that item.")
            else:
                crafting.transfer_item(sb, from_player_id=player_id, to_player_id=rec_map[pick_rec], item_name=pick_item, qty=int(send_qty))
                st.success("Sent.")
                st.rerun()
st.subheader("⛏️ Gathering")

    gather_professions = set(crafting.get_gather_professions(sb))
    available_gather = [p for p in professions if p in gather_professions]

    if not available_gather:
        st.warning("This player has no gathering professions (only crafting).")
    else:
        gp = st.selectbox("Gathering profession", available_gather, key="g_prof")
        roll_total = st.number_input("Roll total (d20 + mods)", min_value=0, max_value=100, value=10, step=1, key="g_roll")

        if st.button("🎲 Roll Gathering"):
            prev = crafting.roll_gathering_preview(sb, player_id, gp, int(roll_total))
            st.session_state["g_prev"] = prev

        prev = st.session_state.get("g_prev")
        if prev:
            if prev.get("failed"):
                st.error("No item found this time.")
            else:
                st.markdown(f"**Result:** {prev['item_name']} (T{prev['tier']} • DC {prev['dc']})")
                if prev.get("description"):
                    st.caption(prev["description"])
                if prev.get("use"):
                    st.caption(prev["use"])
                st.info(f"XP gain: **{prev['xp_gain']}**")

                if st.button("✅ Add to inventory (Gathered)"):
                    crafting.apply_gather_result(sb, player_id, prev)
                    st.session_state.pop("g_prev", None)
                    st.rerun()

# -------------------------
# Discovery: Try = confirm/consume immediately
# -------------------------
with tab_discovery:
    st.subheader("🧪 Recipes (Discovery)")

    all_recipes = crafting.list_all_recipes(sb)
    craft_profs = sorted({r["profession"] for r in all_recipes if r.get("profession")})
    if not craft_profs:
        st.info("No recipes in database yet.")
    else:
        disc_prof = st.selectbox("Crafting profession", craft_profs, key="disc_prof")
        inv = crafting.list_inventory(sb, player_id)
        inv_items = [r["item_name"] for r in inv]

        allow_dupes = crafting.profession_allows_duplicate_components(sb, disc_prof)

        if not inv_items:
            st.warning("You need items in inventory to attempt discovery.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                i1 = st.selectbox("Item 1", inv_items, key="d_i1")
            with c2:
                opts2 = inv_items if allow_dupes else [x for x in inv_items if x != i1]
                i2 = st.selectbox("Item 2", opts2, key="d_i2")
            with c3:
                opts3 = inv_items if allow_dupes else [x for x in inv_items if x not in {i1, i2}]
                i3 = st.selectbox("Item 3", opts3, key="d_i3")

            roll_total = st.number_input("Discovery roll total", min_value=0, max_value=100, value=10, step=1, key="d_roll")

            if st.button("🧩 Try Combination"):
                prev = crafting.discovery_attempt_preview(sb, player_id, disc_prof, i1, i2, i3, int(roll_total))
                # Consume immediately
                crafting.apply_discovery_attempt(sb, player_id, prev)

                st.markdown(f"### Result: **{prev['outcome'].upper()}**")
                if prev.get("hint"):
                    st.info(prev["hint"])
                if prev.get("learned_recipe"):
                    st.success(f"Discovered: **{prev['learned_recipe']}**")

                st.rerun()

# -------------------------
# Craft: show tier + components + filters
# -------------------------
with tab_craft:
    st.subheader("🛠️ Crafting (Known Recipes)")

    known = crafting.list_known_recipes_for_player(sb, player_id)
    all_recipes = crafting.list_all_recipes(sb)
    rec_by_name = {r["name"]: r for r in all_recipes if r.get("name")}
    known_rows = [rec_by_name[n] for n in known if n in rec_by_name]

    if not known_rows:
        st.caption("No known recipes yet. Use Recipes (Discovery) to learn them.")
    else:
        f1, f2, f3 = st.columns([0.35, 0.20, 0.45])
        with f1:
            prof_filter = st.selectbox("Profession", ["All"] + sorted({r["profession"] for r in known_rows}), key="c_prof_f")
        with f2:
            tier_filter = st.selectbox("Tier", ["All"] + [f"T{i}" for i in range(1, 8)], key="c_tier_f")
        with f3:
            search = st.text_input("Search", "", key="c_search")

        def _ok(r):
            if prof_filter != "All" and r.get("profession") != prof_filter:
                return False
            if tier_filter != "All" and int(r.get("tier", 1)) != int(tier_filter[1:]):
                return False
            if search and search.lower() not in r.get("name", "").lower():
                return False
            return True

        filtered = sorted([r for r in known_rows if _ok(r)], key=lambda x: (int(x.get("tier", 1)), x.get("name", "").lower()))
        if not filtered:
            st.caption("No matching recipes.")
        else:
            recipe_name = st.selectbox("Select recipe", [r["name"] for r in filtered], key="craft_pick")
            prev = crafting.craft_preview(sb, player_id, recipe_name)

            st.markdown(f"**Tier:** T{prev['tier']}  |  **Profession:** {prev['profession']}")
            st.markdown("**Components required:**")
            for c in prev["components"]:
                st.write(f"- {c.get('name')} x{int(c.get('qty', 1))}")

            if prev["can_craft"]:
                st.success("All components available.")
            else:
                st.error("Missing components:")
                for m in prev["missing"]:
                    st.write(f"- {m}")

            if st.button("⏳ Start Crafting Timer", disabled=not prev["can_craft"]):
                crafting.start_craft_job(sb, player_id, prev)
                st.rerun()

# -------------------------
# Vendor: 0–3 items, weighted, never above tier cap
# -------------------------
with tab_vendor:
    st.subheader("🧾 Vendor")

    all_recipes = crafting.list_all_recipes(sb)
    craft_profs = sorted({r["profession"] for r in all_recipes if r.get("profession")})
    if not craft_profs:
        st.info("No crafting professions detected from recipes table.")
    else:
        shop_prof = st.selectbox("Shop profession", craft_profs, key="shop_prof")

        if st.button("🎲 Generate/Refresh Vendor Stock (this week)"):
            crafting.refresh_vendor_stock_for_player(sb, player_id, week, shop_prof)
            st.rerun()

        stock = crafting.get_vendor_stock(sb, player_id, week, shop_prof)
        if not stock:
            st.caption("No vendor stock yet. Click refresh.")
        else:
            offers = stock.get("offers") or []
            if not offers:
                st.caption("No offers today.")
            else:
                for off in offers:
                    name = off["item_name"]
                    qty = int(off["qty"])
                    price = off.get("price_gp", None)

                    c1, c2, c3, c4 = st.columns([0.50, 0.15, 0.15, 0.20])
                    with c1:
                        st.write(f"**{name}**")
                    with c2:
                        st.write(f"Qty: {qty}")
                    with c3:
                        st.write(f"Price: {price if price is not None else '—'}")
                    with c4:
                        buy_qty = st.number_input("Buy qty", min_value=1, max_value=qty, value=1, step=1, key=f"buy_{name}")
                        if st.button("Buy", key=f"buybtn_{name}"):
                            crafting.vendor_buy(sb, player_id, week, shop_prof, name, int(buy_qty))
                            st.rerun()

# -------------------------
# Jobs: timers based on your schema (ends_at, done)
# -------------------------
with tab_jobs:
    st.subheader("⏱️ Jobs (Timers)")

    jobs = crafting.list_active_jobs(sb, player_id)
    if not jobs:
        st.caption("No active jobs.")
    else:
        now = datetime.now(timezone.utc)
        for j in jobs:
            ends_at = j.get("ends_at") or j.get("completes_at")
            started_at = j.get("started_at") or j.get("created_at")
            dur = int(j.get("duration_seconds") or 1)

            ends_dt = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00")) if ends_at else now
            start_dt = datetime.fromisoformat(str(started_at).replace("Z", "+00:00")) if started_at else now

            elapsed = max(0, int((now - start_dt).total_seconds()))
            pct = min(1.0, elapsed / max(1, dur))

            st.write(f"**{j.get('recipe_name') or 'Craft job'}**")
            st.progress(pct)

            if now >= ends_dt:
                if st.button("Claim rewards", key=f"claim_{j['id']}"):
                    crafting.claim_job_rewards(sb, player_id, j["id"])
                    st.rerun()
            else:
                st.caption(f"Ends at: {ends_dt}")
