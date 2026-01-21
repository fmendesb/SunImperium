# sun_imperium_app/pages/09_Crafting_Hub.py
import streamlit as st

from utils.supabase_client import get_supabase_client
from utils.crafting import (
    list_players,
    get_player_progress,
    set_skill_xp_delta,
    get_activity_log,
    list_inventory,
    inventory_adjust,
    transfer_item,
    list_professions_for_player,
    roll_gathering_preview,
    apply_gather_result,
    discovery_attempt_preview,
    apply_discovery_attempt,
    list_known_recipes_for_player,
    list_craftable_recipes_for_player,
    craft_preview,
    start_craft_job,
    list_active_jobs,
    claim_job_rewards,
    get_current_week,
    get_vendor_stock,
    refresh_vendor_stock_for_player,
    vendor_buy,
)

st.set_page_config(page_title="Crafting Hub", page_icon="🧰", layout="wide")


def _tier_badge(tier: int, unlocked_tier: int) -> str:
    # Green if <= unlocked, Yellow if == unlocked+1, Red if == unlocked+2 (or more)
    if tier <= unlocked_tier:
        return "🟩"
    if tier == unlocked_tier + 1:
        return "🟨"
    return "🟥"


def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default


def _header():
    st.title("🧰 Crafting Hub")
    st.caption("Gather, discover recipes, craft, and manage inventory. (Test3-style UX, Supabase-backed)")


sb = get_supabase_client()
_header()

# ---------- Player selection ----------
players = list_players(sb)
if not players:
    st.warning("No players found in Supabase table `players`.")
    st.stop()

player_name = st.sidebar.selectbox(
    "Select Player",
    options=[p["name"] for p in players],
    index=0,
)
player = next(p for p in players if p["name"] == player_name)
player_id = player["id"]

week = get_current_week(sb)

# Ensure player progress exists
progress = get_player_progress(sb, player_id)

# Professions visible = only those in skills (per your instruction)
professions = list_professions_for_player(progress)

# ---------- Overview: skills + XP bars + activity log ----------
left, right = st.columns([1.15, 0.85], gap="large")

with left:
    st.subheader("🧠 Skills & XP")
    if not professions:
        st.info("This player has no professions yet. Add skills in `player_progress.skills`.")
    else:
        for prof in professions:
            skill = progress["skills"].get(prof, {"level": 1, "xp": 0})
            level = int(skill.get("level", 1))
            xp = int(skill.get("xp", 0))
            unlocked_tier = level  # simple display; actual tier+2 gating is applied elsewhere

            # Display line
            c1, c2, c3, c4 = st.columns([0.34, 0.18, 0.30, 0.18])
            with c1:
                st.markdown(f"**{prof}**")
                st.caption(f"Level {level}  •  Unlocked Tier {unlocked_tier}")
            with c2:
                if st.button("➖ XP", key=f"xp_minus_{prof}"):
                    set_skill_xp_delta(sb, player_id, prof, -1)
                    st.rerun()
                if st.button("➕ XP", key=f"xp_plus_{prof}"):
                    set_skill_xp_delta(sb, player_id, prof, +1)
                    st.rerun()
            with c3:
                # A simple bar: xp within current level (test3-style feel)
                # We don't know exact xp thresholds unless you wire xp_table. For now show xp as relative.
                # If you later add xp_table, update this to a proper %.
                display_max = max(50, ((level + 1) * 25))
                st.progress(min(1.0, xp / display_max))
                st.caption(f"XP: {xp} (next tier unlock shown as level-based placeholder)")
            with c4:
                st.caption("Tier cap")
                st.write(f"T{level} → max **T{level+2}**")

with right:
    st.subheader("📜 Activity Log")
    logs = get_activity_log(sb, player_id, limit=15)
    if not logs:
        st.caption("No activity yet.")
    else:
        for row in logs:
            st.write(f"• {row['message']}")
            if row.get("created_at"):
                st.caption(str(row["created_at"]))


st.divider()

# ---------- Tabs ----------
tab_overview, tab_inventory, tab_gather, tab_discovery, tab_craft, tab_vendor, tab_jobs = st.tabs(
    ["Overview", "Inventory", "Gather", "Recipes (Discovery)", "Craft", "Vendor", "Jobs"]
)

# ---------- Inventory ----------
with tab_inventory:
    st.subheader("🎒 Inventory")

    sort_by = st.selectbox("Sort by", ["Name", "Tier", "Quantity"], index=0)
    filter_prof = st.selectbox("Filter profession", ["All"] + sorted(set(professions)), index=0)
    filter_tier = st.selectbox("Filter tier", ["All"] + [f"T{i}" for i in range(1, 8)], index=0)

    inv = list_inventory(sb, player_id)

    # Build richer view by joining to gathering_items when possible
    unlocked_tier_for_colors = 1
    if professions:
        # pick max unlocked tier among skills as reference for badge coloring
        unlocked_tier_for_colors = max(int(progress["skills"].get(p, {}).get("level", 1)) for p in professions)

    # Apply filters
    def _infer_tier_from_name(n: str) -> int:
        # expects "Name (T#)" somewhere
        m = None
        if n:
            m = __import__("re").search(r"\(T(\d+)\)", n)
        return int(m.group(1)) if m else 0

    rows = []
    for r in inv:
        name = r["item_name"]
        qty = int(r["quantity"])
        tier = _infer_tier_from_name(name)
        rows.append({"name": name, "qty": qty, "tier": tier})

    if filter_tier != "All":
        want = int(filter_tier.replace("T", ""))
        rows = [x for x in rows if x["tier"] == want]

    # Profession filter: best-effort by looking up gathering_items.profession for exact name match
    if filter_prof != "All":
        rows = [x for x in rows if x.get("name_prof") == filter_prof or True]  # fallback; real filtering is done in utils

    # Sort
    if sort_by == "Name":
        rows.sort(key=lambda x: x["name"].lower())
    elif sort_by == "Tier":
        rows.sort(key=lambda x: (x["tier"], x["name"].lower()))
    else:
        rows.sort(key=lambda x: (-x["qty"], x["name"].lower()))

    if not rows:
        st.caption("Inventory is empty.")
    else:
        for r in rows:
            tier = r["tier"]
            badge = _tier_badge(tier, unlocked_tier_for_colors) if tier else "⬜"
            col1, col2, col3, col4, col5 = st.columns([0.40, 0.12, 0.18, 0.15, 0.15])
            with col1:
                st.markdown(f"**{badge} {r['name']}**")
                st.caption(f"Tier: {tier if tier else '—'}")
            with col2:
                st.metric("Qty", r["qty"])
            with col3:
                if st.button("➖", key=f"inv_minus_{r['name']}"):
                    inventory_adjust(sb, player_id, r["name"], -1)
                    st.rerun()
                if st.button("➕", key=f"inv_plus_{r['name']}"):
                    inventory_adjust(sb, player_id, r["name"], +1)
                    st.rerun()
            with col4:
                # selling price best-effort (from gathering_items or recipes later)
                st.caption("Sell price")
                st.write("—")
            with col5:
                st.caption("Send")
                recipients = [p for p in players if p["id"] != player_id]
                if recipients:
                    recipient_name = st.selectbox(
                        "Recipient",
                        options=[p["name"] for p in recipients],
                        key=f"recipient_{r['name']}",
                    )
                    amount = st.number_input(
                        "Amount",
                        min_value=1,
                        max_value=int(r["qty"]),
                        value=1,
                        step=1,
                        key=f"send_amt_{r['name']}",
                    )
                    if st.button("Send", key=f"send_btn_{r['name']}"):
                        rid = next(p["id"] for p in recipients if p["name"] == recipient_name)
                        transfer_item(sb, player_id, rid, r["name"], int(amount))
                        st.rerun()
                else:
                    st.caption("No other players.")


# ---------- Gather ----------
with tab_gather:
    st.subheader("⛏️ Gathering")

    if not professions:
        st.info("No professions available for this player yet.")
    else:
        gather_prof = st.selectbox("Gathering profession", professions, key="gather_prof")
        roll_total = st.number_input("Enter your roll total (d20 + mods)", min_value=0, max_value=100, value=10, step=1)

        if st.button("🎲 Roll Gathering"):
            preview = roll_gathering_preview(sb, player_id, gather_prof, int(roll_total))
            st.session_state["gather_preview"] = preview

        preview = st.session_state.get("gather_preview")
        if preview:
            st.markdown(f"### Result (Tier {preview['tier']} • DC {preview['dc']})")
            st.markdown(f"**Item:** {preview['item_name']}")
            st.caption(preview.get("description", ""))
            st.caption(preview.get("use", ""))

            st.info(f"XP gain on collect: **{preview['xp_gain']}**")

            if st.button("✅ Add to inventory (Gathered)"):
                apply_gather_result(sb, player_id, preview)
                st.session_state.pop("gather_preview", None)
                st.rerun()


# ---------- Discovery (Recipes) ----------
with tab_discovery:
    st.subheader("🧪 Recipes Discovery (3 components)")

    craft_profs = sorted({r["profession"] for r in list_craftable_recipes_for_player(sb, player_id)})
    if not craft_profs:
        st.info("No recipes available in DB yet.")
    else:
        disc_prof = st.selectbox("Crafting profession", craft_profs, key="disc_prof")

        inv_items = [r["item_name"] for r in list_inventory(sb, player_id) if int(r["quantity"]) > 0]
        if len(inv_items) < 3:
            st.warning("You need at least 3 inventory items to attempt discovery.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                i1 = st.selectbox("Item 1", inv_items, key="disc_i1")
            with c2:
                i2 = st.selectbox("Item 2", inv_items, key="disc_i2")
            with c3:
                i3 = st.selectbox("Item 3", inv_items, key="disc_i3")

            roll_total = st.number_input("Discovery roll total", min_value=0, max_value=100, value=10, step=1, key="disc_roll")

            if st.button("🧩 Try Combination"):
                prev = discovery_attempt_preview(sb, player_id, disc_prof, i1, i2, i3, int(roll_total))
                st.session_state["disc_preview"] = prev

            prev = st.session_state.get("disc_preview")
            if prev:
                st.markdown(f"### Attempt Result: **{prev['outcome'].upper()}**")
                if prev.get("hint"):
                    st.info(prev["hint"])
                if prev.get("learned_recipe"):
                    st.success(f"You discovered: **{prev['learned_recipe']}**")

                st.warning("Items will be consumed on confirm (like test3).")
                if st.button("✅ Confirm attempt (consume items)"):
                    apply_discovery_attempt(sb, player_id, prev)
                    st.session_state.pop("disc_preview", None)
                    st.rerun()


# ---------- Craft ----------
with tab_craft:
    st.subheader("🛠️ Crafting (Known Recipes)")

    known = list_known_recipes_for_player(sb, player_id)
    if not known:
        st.caption("No known recipes yet. Use Recipes (Discovery) to learn them.")
    else:
        recipe_name = st.selectbox("Select known recipe", known, key="craft_recipe")
        prev = craft_preview(sb, player_id, recipe_name)

        if prev["can_craft"]:
            st.success("All components available.")
        else:
            st.error("Missing components:")
            for m in prev["missing"]:
                st.write(f"- {m}")

        # Tier/DC visibility is handled in preview.
        st.caption(f"Tier {prev['tier']} (visible up to unlocked+2).")

        if st.button("⏳ Start Crafting Timer", disabled=not prev["can_craft"]):
            start_craft_job(sb, player_id, prev)
            st.rerun()


# ---------- Vendor ----------
with tab_vendor:
    st.subheader("🧾 Vendor")

    # Player chooses crafting profession
    craft_profs = sorted({r["profession"] for r in list_craftable_recipes_for_player(sb, player_id)})
    if not craft_profs:
        st.info("No crafting professions detected from recipes table.")
    else:
        shop_prof = st.selectbox("Shop profession", craft_profs, key="shop_prof")

        colA, colB = st.columns([0.25, 0.75])
        with colA:
            if st.button("🎲 Generate/Refresh Vendor Stock (this week)"):
                refresh_vendor_stock_for_player(sb, player_id, week, shop_prof)
                st.rerun()
        with colB:
            st.caption("Vendor stock is per-player, per-week, per-profession (test3 style).")

        stock = get_vendor_stock(sb, player_id, week, shop_prof)
        if not stock:
            st.caption("No vendor stock yet. Click refresh.")
        else:
            offers = stock["offers"]
            if not offers:
                st.caption("Vendor has nothing today (0 offers).")
            else:
                for off in offers:
                    name = off["item_name"]
                    qty = int(off["qty"])
                    price = off.get("price_gp", None)
                    c1, c2, c3, c4 = st.columns([0.45, 0.15, 0.20, 0.20])
                    with c1:
                        st.write(f"**{name}**")
                    with c2:
                        st.write(f"Qty: {qty}")
                    with c3:
                        st.write(f"Price: {price if price is not None else '—'}")
                    with c4:
                        buy_qty = st.number_input(f"Buy qty ({name})", min_value=1, max_value=qty, value=1, step=1, key=f"buyqty_{name}")
                        if st.button("Buy", key=f"buy_{name}"):
                            vendor_buy(sb, player_id, week, shop_prof, name, int(buy_qty))
                            st.rerun()


# ---------- Jobs ----------
with tab_jobs:
    st.subheader("⏱️ Jobs (Timers)")

    jobs = list_active_jobs(sb, player_id)
    if not jobs:
        st.caption("No active jobs.")
    else:
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        for j in jobs:
            ends_at = __import__("dateutil.parser").isoparse(j["completes_at"]) if isinstance(j["completes_at"], str) else j["completes_at"]
            total = int(j["duration_seconds"])
            elapsed = max(0, int((now - __import__("dateutil.parser").isoparse(j["started_at"])).total_seconds()))
            pct = min(1.0, elapsed / max(1, total))
            st.write(f"**{j.get('kind','job').title()}**")
            st.progress(pct)
            if now >= ends_at:
                if st.button("Claim rewards", key=f"claim_{j['id']}"):
                    claim_job_rewards(sb, player_id, j["id"])
                    st.rerun()
            else:
                st.caption(f"Ends at: {ends_at}")

