# sun_imperium_app/utils/crafting.py
import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

# --------------------------
# Helpers
# --------------------------

TIER_RE = re.compile(r"\(T(\d+)\)")


def _tier_from_name(name: str) -> int:
    m = TIER_RE.search(name or "")
    return int(m.group(1)) if m else 0


def _base_name(name: str) -> str:
    # Strip tier suffix " (T#)"
    return re.sub(r"\s*\(T\d+\)\s*$", "", name or "").strip()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _clamp(x: int, a: int, b: int) -> int:
    return max(a, min(b, x))


# --------------------------
# Supabase wrappers
# --------------------------

def list_players(sb) -> List[Dict[str, Any]]:
    res = sb.table("players").select("id,name").order("name").execute()
    return res.data or []


def get_current_week(sb) -> int:
    # Try app_settings first (v1), else fallback to app_state
    try:
        r = sb.table("app_settings").select("current_week").limit(1).execute()
        if r.data:
            return int(r.data[0]["current_week"])
    except Exception:
        pass
    try:
        r = sb.table("app_state").select("current_week").eq("id", 1).single().execute()
        return int(r.data["current_week"])
    except Exception:
        return 1


def get_player_progress(sb, player_id: str) -> Dict[str, Any]:
    r = sb.table("player_progress").select("player_id,skills,discovered_recipes,known_recipes").eq("player_id", player_id).execute()
    if r.data:
        row = r.data[0]
        # normalize
        row["skills"] = row.get("skills") or {}
        # some schemas used discovered_recipes; some use known_recipes
        row["known_recipes"] = row.get("known_recipes") or row.get("discovered_recipes") or []
        row["discovered_recipes"] = row.get("discovered_recipes") or []
        return row

    # create row if missing
    new_row = {"player_id": player_id, "skills": {}, "known_recipes": [], "discovered_recipes": []}
    sb.table("player_progress").insert(new_row).execute()
    return new_row


def list_professions_for_player(progress: Dict[str, Any]) -> List[str]:
    skills = progress.get("skills") or {}
    return sorted([k for k in skills.keys() if k and isinstance(skills.get(k), dict)])


def set_skill_xp_delta(sb, player_id: str, profession: str, delta_xp: int) -> None:
    prog = get_player_progress(sb, player_id)
    skills = prog.get("skills") or {}
    s = skills.get(profession) or {"level": 1, "xp": 0}
    s["level"] = int(s.get("level", 1))
    s["xp"] = int(s.get("xp", 0)) + int(delta_xp)
    if s["xp"] < 0:
        s["xp"] = 0
    skills[profession] = s

    sb.table("player_progress").update({"skills": skills}).eq("player_id", player_id).execute()
    log(sb, player_id, "xp", f"{profession}: XP {'+' if delta_xp>=0 else ''}{delta_xp}", {"profession": profession, "delta": delta_xp})


def log(sb, player_id: str, kind: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
    sb.table("activity_log").insert({
        "player_id": player_id,
        "kind": kind,
        "message": message,
        "meta": meta or {}
    }).execute()


def get_activity_log(sb, player_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    r = sb.table("activity_log").select("created_at,message,kind,meta").eq("player_id", player_id).order("created_at", desc=True).limit(limit).execute()
    return r.data or []


# --------------------------
# Inventory
# --------------------------

def list_inventory(sb, player_id: str) -> List[Dict[str, Any]]:
    r = sb.table("player_inventory").select("item_name,quantity").eq("player_id", player_id).execute()
    return r.data or []


def inventory_adjust(sb, player_id: str, item_name: str, delta: int) -> None:
    # upsert logic
    inv = sb.table("player_inventory").select("quantity").eq("player_id", player_id).eq("item_name", item_name).execute()
    cur = int(inv.data[0]["quantity"]) if inv.data else 0
    new = max(0, cur + int(delta))

    if inv.data:
        sb.table("player_inventory").update({"quantity": new}).eq("player_id", player_id).eq("item_name", item_name).execute()
    else:
        sb.table("player_inventory").insert({"player_id": player_id, "item_name": item_name, "quantity": new}).execute()

    log(sb, player_id, "inventory", f"{'Added' if delta>0 else 'Removed'} {abs(delta)} x {item_name}", {"item_name": item_name, "delta": delta})


def transfer_item(sb, from_player_id: str, to_player_id: str, item_name: str, qty: int) -> None:
    qty = int(qty)
    if qty <= 0:
        return
    # remove from sender
    inv = sb.table("player_inventory").select("quantity").eq("player_id", from_player_id).eq("item_name", item_name).execute()
    cur = int(inv.data[0]["quantity"]) if inv.data else 0
    if cur < qty:
        qty = cur
    sb.table("player_inventory").update({"quantity": cur - qty}).eq("player_id", from_player_id).eq("item_name", item_name).execute()

    # add to receiver
    inv2 = sb.table("player_inventory").select("quantity").eq("player_id", to_player_id).eq("item_name", item_name).execute()
    cur2 = int(inv2.data[0]["quantity"]) if inv2.data else 0
    if inv2.data:
        sb.table("player_inventory").update({"quantity": cur2 + qty}).eq("player_id", to_player_id).eq("item_name", item_name).execute()
    else:
        sb.table("player_inventory").insert({"player_id": to_player_id, "item_name": item_name, "quantity": qty}).execute()

    log(sb, from_player_id, "transfer", f"Sent {qty} x {item_name}", {"to_player_id": to_player_id, "item_name": item_name, "qty": qty})
    log(sb, to_player_id, "transfer", f"Received {qty} x {item_name}", {"from_player_id": from_player_id, "item_name": item_name, "qty": qty})


# --------------------------
# Recipes + Craftables
# --------------------------

def list_craftable_recipes_for_player(sb, player_id: str) -> List[Dict[str, Any]]:
    # basic: return all recipes; UI will filter by profession/known recipes
    r = sb.table("recipes").select("name,profession,tier,components,base_price_gp,vendor_price_gp,sale_price_gp,category,craft_type,rarity").execute()
    return r.data or []


def list_known_recipes_for_player(sb, player_id: str) -> List[str]:
    prog = get_player_progress(sb, player_id)
    known = prog.get("known_recipes") or prog.get("discovered_recipes") or []
    return sorted(list(dict.fromkeys(known)))


def _set_known_recipes(sb, player_id: str, known: List[str]) -> None:
    # store in known_recipes if column exists, else discovered_recipes
    # We'll just try update both safely.
    sb.table("player_progress").update({"known_recipes": known, "discovered_recipes": known}).eq("player_id", player_id).execute()


# --------------------------
# Gathering (Test3-style)
# --------------------------

# You asked to copy test3 thresholds. This is a placeholder mapping that will be refined to exact values.
# Format: (min_roll_inclusive, tier_delta) with tier_delta in {0,1,2}
TEST3_GATHER_THRESHOLDS = [
    (0, 0),
    (15, 1),
    (20, 2),
]


def _tier_delta_from_roll(roll_total: int) -> int:
    td = 0
    for th, d in TEST3_GATHER_THRESHOLDS:
        if roll_total >= th:
            td = d
    return td


def roll_gathering_preview(sb, player_id: str, profession: str, roll_total: int) -> Dict[str, Any]:
    prog = get_player_progress(sb, player_id)
    skill = (prog.get("skills") or {}).get(profession) or {"level": 1, "xp": 0}
    level = int(skill.get("level", 1))
    unlocked_tier = level

    # max tier visible = unlocked + 2 (your rule)
    td = _tier_delta_from_roll(int(roll_total))
    tier = _clamp(unlocked_tier + td, 1, unlocked_tier + 2)

    # DC mapping (your rule)
    dc = 10 if tier == unlocked_tier else (15 if tier == unlocked_tier + 1 else 20)

    items = sb.table("gathering_items").select("name,description,use,tier,profession").eq("profession", profession).eq("tier", tier).execute().data or []
    if not items:
        # fallback: any profession at that tier
        items = sb.table("gathering_items").select("name,description,use,tier,profession").eq("tier", tier).execute().data or []

    pick = random.choice(items) if items else {"name": f"Unknown Resource (T{tier})", "description": "", "use": ""}
    xp_gain = _xp_gain_for_gather(tier)

    return {
        "profession": profession,
        "roll_total": int(roll_total),
        "unlocked_tier": unlocked_tier,
        "tier": tier,
        "dc": dc,
        "item_name": pick["name"],
        "description": pick.get("description", ""),
        "use": pick.get("use", ""),
        "xp_gain": xp_gain,
    }


def _xp_gain_for_gather(tier: int) -> int:
    # Placeholder; replace with exact test3 values if different.
    return {1: 1, 2: 2, 3: 3, 4: 4, 5: 6, 6: 8, 7: 10}.get(int(tier), 1)


def apply_gather_result(sb, player_id: str, preview: Dict[str, Any]) -> None:
    inventory_adjust(sb, player_id, preview["item_name"], +1)
    # add xp to that profession
    set_skill_xp_delta(sb, player_id, preview["profession"], int(preview.get("xp_gain", 1)))
    log(sb, player_id, "gather", f"Gathered {preview['item_name']} (T{preview['tier']})", preview)


# --------------------------
# Discovery (Test3-style)
# --------------------------

def discovery_attempt_preview(
    sb,
    player_id: str,
    profession: str,
    item1: str,
    item2: str,
    item3: str,
    roll_total: int
) -> Dict[str, Any]:
    # Compare base names (ignore tiers)
    chosen = sorted([_base_name(item1), _base_name(item2), _base_name(item3)])

    # Find recipes of that profession with exactly 3 components (test3 style)
    recs = sb.table("recipes").select("name,tier,profession,components").eq("profession", profession).execute().data or []

    match = None
    best_overlap = 0
    best_recipe = None

    for r in recs:
        comps = r.get("components") or []
        # components may arrive as dict/list from jsonb; ensure list
        if isinstance(comps, str):
            try:
                comps = json.loads(comps)
            except Exception:
                comps = []
        comp_names = sorted([_base_name(c.get("name", "")) for c in comps][:3])
        overlap = len(set(chosen).intersection(set(comp_names)))
        if overlap > best_overlap:
            best_overlap = overlap
            best_recipe = r

        if comp_names == chosen:
            match = r
            break

    # DC based on tier visibility: unlocked tier +2 max, DC 10/15/20
    prog = get_player_progress(sb, player_id)
    # For discovery: use profession skill if present else default level1
    skill = (prog.get("skills") or {}).get(profession) or {"level": 1, "xp": 0}
    unlocked_tier = int(skill.get("level", 1))
    tier_cap = unlocked_tier + 2

    learned_recipe = None
    outcome = "fail"
    hint = None

    if match:
        tier = int(match.get("tier", 1))
        if tier > tier_cap:
            outcome = "fail"
            hint = f"That combination feels beyond your current mastery (cap T{tier_cap})."
        else:
            # Determine DC by tier relative to unlocked
            if tier == unlocked_tier:
                dc = 10
            elif tier == unlocked_tier + 1:
                dc = 15
            else:
                dc = 20
            if int(roll_total) >= dc:
                outcome = "success"
                learned_recipe = match["name"]
            else:
                outcome = "fail"
                hint = "The pattern is real, but your execution was lacking."
    else:
        # partial hint logic: if 2 overlap and roll is high, tell them 2 match
        if best_overlap >= 2 and int(roll_total) >= 18:
            outcome = "partial_hint"
            # find two that overlap
            comps = best_recipe.get("components") if best_recipe else []
            if isinstance(comps, str):
                try:
                    comps = json.loads(comps)
                except Exception:
                    comps = []
            comp_set = set([_base_name(c.get("name", "")) for c in comps][:3])
            good = [x for x in chosen if x in comp_set]
            hint = f"Two components resonate together: **{good[0]}** and **{good[1]}**. The third is wrong."
        else:
            hint = "Nothing clicks. Maybe try a different combination."

    xp_gain = _xp_gain_for_discovery(outcome)

    return {
        "profession": profession,
        "roll_total": int(roll_total),
        "items": [item1, item2, item3],
        "outcome": outcome,
        "hint": hint,
        "learned_recipe": learned_recipe,
        "xp_gain": xp_gain,
    }


def _xp_gain_for_discovery(outcome: str) -> int:
    # Placeholder; copy test3 values if different.
    return {"success": 3, "partial_hint": 1, "fail": 1}.get(outcome, 1)


def apply_discovery_attempt(sb, player_id: str, preview: Dict[str, Any]) -> None:
    # consume the items (always)
    for it in preview["items"]:
        inventory_adjust(sb, player_id, it, -1)

    # grant xp to that profession
    set_skill_xp_delta(sb, player_id, preview["profession"], int(preview.get("xp_gain", 1)))

    # learn recipe if success
    if preview.get("learned_recipe"):
        known = list_known_recipes_for_player(sb, player_id)
        if preview["learned_recipe"] not in known:
            known.append(preview["learned_recipe"])
            _set_known_recipes(sb, player_id, known)
        log(sb, player_id, "discover", f"Discovered recipe: {preview['learned_recipe']}", preview)
    else:
        log(sb, player_id, "discover", f"Discovery attempt: {preview['outcome']}", preview)

    # store attempt record if table exists
    try:
        sb.table("recipe_discovery_logs").insert({
            "player_id": player_id,
            "profession": preview["profession"],
            "item1": preview["items"][0],
            "item2": preview["items"][1],
            "item3": preview["items"][2],
            "roll_total": preview["roll_total"],
            "outcome": preview["outcome"],
            "hint": preview.get("hint", None),
        }).execute()
    except Exception:
        pass


# --------------------------
# Crafting (Known recipes)
# --------------------------

def craft_preview(sb, player_id: str, recipe_name: str) -> Dict[str, Any]:
    r = sb.table("recipes").select("name,tier,profession,components,output_qty").eq("name", recipe_name).limit(1).execute()
    if not r.data:
        return {"can_craft": False, "missing": ["Recipe not found"], "tier": 1}

    rec = r.data[0]
    comps = rec.get("components") or []
    if isinstance(comps, str):
        try:
            comps = json.loads(comps)
        except Exception:
            comps = []

    inv = {x["item_name"]: int(x["quantity"]) for x in list_inventory(sb, player_id)}
    missing = []
    for c in comps:
        nm = c.get("name")
        q = int(c.get("qty", 1))
        if inv.get(nm, 0) < q:
            missing.append(f"{nm} x{q} (have {inv.get(nm,0)})")

    return {
        "recipe_name": recipe_name,
        "tier": int(rec.get("tier", 1)),
        "profession": rec.get("profession"),
        "components": comps,
        "output_qty": int(rec.get("output_qty", 1)),
        "can_craft": len(missing) == 0,
        "missing": missing,
    }


def _craft_duration_seconds(tier: int) -> int:
    # Your timer rules can be inserted here. Placeholder: T6=2h
    if int(tier) == 6:
        return 2 * 60 * 60
    # default: 10 minutes per tier
    return int(tier) * 10 * 60


def start_craft_job(sb, player_id: str, preview: Dict[str, Any]) -> None:
    # consume components immediately (test3 style)
    for c in preview["components"]:
        inventory_adjust(sb, player_id, c.get("name"), -int(c.get("qty", 1)))

    tier = int(preview["tier"])
    dur = _craft_duration_seconds(tier)
    ends_at = _now_utc() + timedelta(seconds=dur)

    sb.table("crafting_jobs").insert({
        "player_id": player_id,
        "kind": "craft",
        "status": "active",
        "recipe_name": preview["recipe_name"],
        "duration_seconds": dur,
        "completes_at": ends_at.isoformat(),
        "detail": {"tier": tier, "profession": preview["profession"]},
        "result": {"output_qty": preview["output_qty"]},
    }).execute()

    log(sb, player_id, "craft", f"Started crafting: {preview['recipe_name']}", preview)


def list_active_jobs(sb, player_id: str) -> List[Dict[str, Any]]:
    r = sb.table("crafting_jobs").select("*").eq("player_id", player_id).eq("status", "active").order("created_at", desc=True).execute()
    return r.data or []


def claim_job_rewards(sb, player_id: str, job_id: str) -> None:
    job = sb.table("crafting_jobs").select("*").eq("id", job_id).single().execute().data
    if not job:
        return

    # only allow if complete
    ends = job.get("completes_at")
    if isinstance(ends, str):
        ends_dt = datetime.fromisoformat(ends.replace("Z", "+00:00"))
    else:
        ends_dt = ends
    if _now_utc() < ends_dt:
        return

    kind = job.get("kind")
    if kind == "craft":
        recipe_name = job.get("recipe_name")
        qty = int((job.get("result") or {}).get("output_qty", 1))
        # Output item name = recipe name (test3 style) unless you map differently
        inventory_adjust(sb, player_id, recipe_name, +qty)
        # XP gain: placeholder; adjust to test3
        prof = (job.get("detail") or {}).get("profession")
        if prof:
            set_skill_xp_delta(sb, player_id, prof, _xp_gain_for_craft(int((job.get("detail") or {}).get("tier", 1))))
        log(sb, player_id, "craft", f"Craft completed: {recipe_name}", {"qty": qty})

    sb.table("crafting_jobs").update({"status": "completed"}).eq("id", job_id).execute()


def _xp_gain_for_craft(tier: int) -> int:
    # Placeholder; copy test3 values if different.
    return {1: 2, 2: 3, 3: 4, 4: 6, 5: 8, 6: 12, 7: 15}.get(int(tier), 2)


# --------------------------
# Vendor (Per player/week/profession)
# --------------------------

def refresh_vendor_stock_for_player(sb, player_id: str, week: int, shop_profession: str) -> None:
    # Build list of component names used by this profession's recipes
    recs = sb.table("recipes").select("components,profession").eq("profession", shop_profession).execute().data or []
    comp_names = set()
    for r in recs:
        comps = r.get("components") or []
        if isinstance(comps, str):
            try:
                comps = json.loads(comps)
            except Exception:
                comps = []
        for c in comps:
            nm = c.get("name")
            if nm:
                comp_names.add(nm)

    comp_names = list(comp_names)
    random.shuffle(comp_names)

    # Determine tier cap = min(unlocked+2, 2) (your rule: vendor never above T2 player level)
    prog = get_player_progress(sb, player_id)
    # use max level among skills as base; if none, level1
    levels = [int(v.get("level", 1)) for v in (prog.get("skills") or {}).values() if isinstance(v, dict)]
    unlocked_tier = max(levels) if levels else 1
    tier_cap = min(unlocked_tier + 2, 2)

    # Choose 0-3 items (weighted to know/low)
    n = random.choices([0, 1, 2, 3], weights=[20, 45, 25, 10], k=1)[0]
    offers = []
    for nm in comp_names[:n]:
        tier = _tier_from_name(nm)
        if tier and tier > tier_cap:
            continue
        qty = random.choices([1, 2, 3, 4], weights=[55, 25, 15, 5], k=1)[0]
        # price from gathering_items or fallback
        price = _vendor_price_for_item(sb, nm)
        offers.append({"item_name": nm, "qty": qty, "price_gp": price})

    # persist (uses existing vendor_stock table if present)
    try:
        # your schema earlier had vendor_stock(week) only; we upsert via unique constraint if you added it
        sb.table("vendor_stock").upsert({
            "player_id": player_id,
            "week": int(week),
            "shop_profession": shop_profession,
            "offers": offers
        }).execute()
    except Exception:
        # fallback: store in activity log only
        pass

    log(sb, player_id, "vendor", f"Vendor refreshed for {shop_profession} (Week {week})", {"offers": offers})


def _vendor_price_for_item(sb, item_name: str) -> float:
    # Look up vendor_price_gp from gathering_items
    r = sb.table("gathering_items").select("vendor_price_gp").eq("name", item_name).limit(1).execute()
    if r.data:
        try:
            return float(r.data[0].get("vendor_price_gp", 0) or 0)
        except Exception:
            return 0.0
    return 0.0


def get_vendor_stock(sb, player_id: str, week: int, shop_profession: str) -> Optional[Dict[str, Any]]:
    try:
        r = sb.table("vendor_stock").select("offers").eq("player_id", player_id).eq("week", int(week)).eq("shop_profession", shop_profession).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def vendor_buy(sb, player_id: str, week: int, shop_profession: str, item_name: str, qty: int) -> None:
    qty = int(qty)
    stock = get_vendor_stock(sb, player_id, week, shop_profession)
    if not stock:
        return

    offers = stock.get("offers") or []
    new_offers = []
    bought = False
    for o in offers:
        if o.get("item_name") == item_name and not bought:
            have = int(o.get("qty", 0))
            take = min(have, qty)
            if take > 0:
                inventory_adjust(sb, player_id, item_name, +take)
                # vendor stock decreases
                remain = have - take
                if remain > 0:
                    o["qty"] = remain
                    new_offers.append(o)
                bought = True
                log(sb, player_id, "vendor", f"Bought {take} x {item_name}", {"item_name": item_name, "qty": take})
            else:
                new_offers.append(o)
        else:
            new_offers.append(o)

    # update offers
    try:
        sb.table("vendor_stock").update({"offers": new_offers}).eq("player_id", player_id).eq("week", int(week)).eq("shop_profession", shop_profession).execute()
    except Exception:
        pass
