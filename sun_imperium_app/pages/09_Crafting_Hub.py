import streamlit as st
from datetime import datetime, timezone

from utils.supabase_client import get_supabase

# Import crafting utils with backwards-compatible fallbacks
import utils.crafting as crafting

ensure_player_progress = getattr(crafting, "ensure_player_progress", None) or getattr(crafting, "get_or_create_player_progress", None)
if ensure_player_progress is None:
    raise ImportError("utils.crafting must define ensure_player_progress (or get_or_create_player_progress)")

list_players = crafting.list_players
set_skill_xp_delta = crafting.set_skill_xp_delta
get_activity_log = crafting.get_activity_log
list_inventory = crafting.list_inventory
inventory_adjust = crafting.inventory_adjust
transfer_item = crafting.transfer_item
list_professions_for_player = crafting.list_professions_for_player
get_gather_professions = crafting.get_gather_professions
roll_gathering_preview = crafting.roll_gathering_preview
apply_gather_result = crafting.apply_gather_result
profession_allows_duplicate_components = crafting.profession_allows_duplicate_components
discovery_attempt_preview = crafting.discovery_attempt_preview
apply_discovery_attempt = crafting.apply_discovery_attempt
list_known_recipes_for_player = crafting.list_known_recipes_for_player
list_all_recipes = crafting.list_all_recipes
craft_preview = crafting.craft_preview
start_craft_job = crafting.start_craft_job
list_active_jobs = crafting.list_active_jobs
claim_job_rewards = crafting.claim_job_rewards
get_current_week = crafting.get_current_week
get_vendor_stock = crafting.get_vendor_stock
refresh_vendor_stock_for_player = crafting.refresh_vendor_stock_for_player
vendor_buy = crafting.vendor_buy
max_tier_for_level = crafting.max_tier_for_level
xp_required_for_level = crafting.xp_required_for_level

st.set_page_config(page_title="Crafting Hub", page_icon="🧰", layout="wide")
st.title("🧰 Crafting Hub")
st.caption("Gather, discover recipes, craft, and manage inventory. (Test3-style UX, Supabase-backed)")

sb = get_supabase()

def _tier_badge(tier: int, unlocked_tier: int) -> str:
    if tier <= unlocked_tier:
        return "🟩"
    if tier == unlocked_tier + 1:
        return "🟨"
    return "🟥"

# ---------- Player selection ----------
players = list_players(sb)
if not players:
    st.warning("No players found in Supabase table `players`.")
    st.stop()

player_name = st.sidebar.selectbox("Select Player", options=[p["name"] for p in players], index=0)
player = next(p for p in players if p["name"] == player_name)
player_id = player["id"]

week = get_current_week(sb)

# Ensure progress exists
progress = ensure_player_progress(sb, player_id)
professions = list_professions_for_player(progress)

# ---------- Top overview + collapsible activity log ----------
left, right = st.columns([1.15, 0.85], gap="large")

with left:
    st.subheader("🧠 Skills & XP")
    if not professions:
        st.info("This player has no professions yet. Add skills in `player_progress.skills`.")
    else:
        for prof in professions:
            skill = (progress.get("skills") or {}).get(prof) or {"level": 1, "xp": 0}
            level = int(skill.get("level", 1))
            xp = int(skill.get("xp", 0))
            unlocked_tier = max_tier_for_level(sb, level)
            visible_cap = unlocked_tier + 2

            next_level = min(20, level + 1)
            xp_needed_next = xp_required_for_level(sb, next_level)
            xp_needed_this = xp_required_for_level(sb, level)

            denom = max(1, xp_needed_next - xp_needed_this)
            num = max(0, xp - xp_needed_this)
            pct = min(1.0, num / denom)

            c1, c2, c3, c4 = st.columns([0.34, 0.18, 0.30, 0.18])
            with c1:
                st.markdown(f"**{prof}**")
                st.caption(f"Level {level} • Unlocked Tier {unlocked_tier} • Visible up to T{visible_cap}")
            with c2:
                if st.button("➖ XP", key=f"xp_minus_{prof}"):
                    set_skill_xp_delta(sb, player_id, prof, -1)
                    st.rerun()
                if st.button("➕ XP", key=f"xp_plus_{prof}"):
                    set_skill_xp_delta(sb, player_id, prof, +1)
                    st.rerun()
            with c3:
                st.progress(pct)
                st.caption(f"XP {xp} • next level at {xp_needed_next}")
            with c4:
                st.caption("Tier cap")
                st.write(f"T{unlocked_tier} → max **T{visible_cap}**")

with right:
    with st.expander("📜 Activity Log", expanded=False):
        logs = get_activity_log(sb, player_id, limit=25)
        if not logs:
            st.caption("No activity yet.")
        else:
            for row in logs:
                st.write(f"• {row['message']}")
                if row.get("created_at"):
                    st.caption(str(row["created_at"]))

st.divider()

# ---------- Tabs (NO overview tab) ----------
tab_inventory, tab_gather, tab_discovery, tab_craft, tab_vendor, tab_jobs = st.tabs(
    ["Inventory", "Gather", "Recipes (Discovery)", "Craft", "Vendor", "Jobs"]
)

# ---------- Inventory ----------
with tab_inventory:
    st.subheader("🎒 Inventory")
    sort_by = st.selectbox("Sort by", ["Name", "Tier", "Quantity"], index=0)
    filter_tier = st.selectbox("Filter tier", ["All"] + [f"T{i}" for i in range(1, 8)], index=0)

    inv = list_inventory(sb, player_id)

    def infer_tier(n: str) -> int:
        import re
        m = re.search(r"\(T(\d+)\)", n or "")
        return int(m.group(1)) if m else 0

    rows = [{"name": r["item_name"], "qty": int(r["quantity"]), "tier": infer_tier(r["item_name"])} for r in inv]
    if filter_tier != "All":
        want = int(filter_tier.replace("T", ""))
        rows = [x for x in rows if x["tier"] == want]

    if sort_by == "Name":
        rows.sort(key=lambda x: x["name"].lower())
    elif sort_by == "Tier":
        rows.sort(key=lambda x: (x["tier"], x["name"].lower()))
    else:
        rows.sort(key=lambda x: (-x["qty"], x["name"].lower()))

    unlocked_tier_for_colors = 1
    if professions:
        unlocked_tier_for_colors = max(
            max_tier_for_level(sb, int((progress.get("skills") or {}).get(p, {}).get("level", 1)))
            for p in professions
        )

    if not rows:
        st.caption("Inventory is empty.")
    else:
        for r in rows:
            tier = r["tier"]
            badge = _tier_badge(tier, unlocked_tier_for_colors) if tier else "⬜"

            col1, col2, col3, col4 = st.columns([0.55, 0.10, 0.15, 0.20])
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
                recipients = [p for p in players if p["id"] != player_id]
                if recipients and r["qty"] > 0:
                    recipient_name = st.selectbox("Recipient", options=[p["name"] for p in recipients], key=f"recipient_{r['name']}")
                    amount = st.number_input("Amount", min_value=1, max_value=int(r["qty"]), value=1, step=1, key=f"send_amt_{r['name']}")
                    if st.button("Send", key=f"send_btn_{r['name']}"):
                        rid = next(p["id"] for p in recipients if p["name"] == recipient_name)
                        transfer_item(sb, player_id, rid, r["name"], int(amount))
                        st.rerun()
                else:
                    st.caption("No other players / qty is 0.")

# ---------- Gather (ONLY gathering professions) ----------
with tab_gather:
    st.subheader("⛏️ Gathering")
    if not professions:
        st.info("No professions available for this player yet.")
    else:
        gatherable_set = set(get_gather_professions(sb))
        gatherable = [p for p in professions if p in gatherable_set]

        if not gatherable:
            st.warning("This player has no gathering professions (only crafting).")
        else:
            gather_prof = st.selectbox("Gathering profession", gatherable, key="gather_prof")
            roll_total = st.number_input("Enter your roll total (d20 + mods)", min_value=0, max_value=100, value=10, step=1)

            if st.button("🎲 Roll Gathering"):
                preview = roll_gathering_preview(sb, player_id, gather_prof, int(roll_total))
                st.session_state["gather_preview"] = preview

            preview = st.session_state.get("gather_preview")
            if preview:
                if preview.get("failed"):
                    st.error("Gathering failed! You didn’t find anything this time.")
                else:
                    st.markdown(f"### Result (Tier {preview['tier']} • DC {preview['dc']})")
                    st.markdown(f"**Item:** {preview['item_name']}")
                    st.caption(preview.get("description", ""))
                    st.caption(preview.get("use", ""))
                    st.info(f"XP gain on collect: **{preview['xp_gain']}**")

                    if st.button("✅ Add to inventory (Gathered)"):
                        apply_gather_result(sb, player_id, preview)
                        st.session_state.pop("gather_preview", None)
                        st.rerun()

# ---------- Discovery (3 items) ----------
with tab_discovery:
    st.subheader("🧪 Recipes Discovery (3 components)")
    all_recipes = list_all_recipes(sb)
    craft_profs = sorted({r["profession"] for r in all_recipes if r.get("profession")})

    if not craft_profs:
        st.info("No recipes available in DB yet.")
    else:
        disc_prof = st.selectbox("Crafting profession", craft_profs, key="disc_prof")

        inv_items = [r["item_name"] for r in list_inventory(sb, player_id) if int(r["quantity"]) > 0]
        inv_items = list(dict.fromkeys(inv_items))

        allow_dupes = profession_allows_duplicate_components(sb, disc_prof)

        if len(inv_items) < 3 and not allow_dupes:
            st.warning("You need at least 3 different inventory items to attempt discovery.")
        elif len(inv_items) < 1:
            st.warning("You need items in inventory to attempt discovery.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                i1 = st.selectbox("Item 1", inv_items, key="disc_i1")
            with c2:
                opts2 = inv_items if allow_dupes else [x for x in inv_items if x != i1]
                i2 = st.selectbox("Item 2", opts2, key="disc_i2")
            with c3:
                opts3 = inv_items if allow_dupes else [x for x in inv_items if x not in {i1, i2}]
                i3 = st.selectbox("Item 3", opts3, key="disc_i3")

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

        if st.button("⏳ Start Crafting Timer", disabled=not prev["can_craft"]):
            start_craft_job(sb, player_id, prev)
            st.rerun()

# ---------- Vendor ----------
with tab_vendor:
    st.subheader("🧾 Vendor")
    all_recipes = list_all_recipes(sb)
    craft_profs = sorted({r["profession"] for r in all_recipes if r.get("profession")})

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
            st.caption("Vendor stock is per-player, per-week, per-profession.")

        stock = get_vendor_stock(sb, player_id, week, shop_prof)
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
        now = datetime.now(timezone.utc)
        for j in jobs:
            ends_at = datetime.fromisoformat(str(j.get("completes_at")).replace("Z", "+00:00"))
            started_at = datetime.fromisoformat(str(j.get("started_at")).replace("Z", "+00:00")) if j.get("started_at") else now
            total = int(j.get("duration_seconds") or 1)
            elapsed = max(0, int((now - started_at).total_seconds()))
            pct = min(1.0, elapsed / max(1, total))
            st.write(f"**{str(j.get('kind','job')).title()}**")
            st.progress(pct)

            if now >= ends_at:
                if st.button("Claim rewards", key=f"claim_{j['id']}"):
                    claim_job_rewards(sb, player_id, j["id"])
                    st.rerun()
            else:
                st.caption(f"Ends at: {ends_at}")
