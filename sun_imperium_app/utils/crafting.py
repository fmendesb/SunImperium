# sun_imperium_app/utils/crafting.py
import json
import random
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

TIER_RE = re.compile(r"\(T(\d+)\)")


# ---------------------------
# Supabase execute retry
# ---------------------------


def _sb_execute(req, *, retries: int = 3, base_sleep: float = 0.25):
    """Execute a PostgREST request with small retries.

    Streamlit Cloud occasionally throws transient httpx.ReadError / transport
    errors. Retrying a couple times makes the UX far less brittle.
    """

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return req.execute()
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = f"{type(e).__name__}: {e}"
            is_transient = any(
                k in msg
                for k in (
                    "ReadError",
                    "ConnectError",
                    "RemoteProtocolError",
                    "Server disconnected",
                    "timed out",
                    "Timeout",
                    "502",
                    "503",
                    "504",
                )
            )
            if (attempt + 1) >= retries or not is_transient:
                raise
            time.sleep(base_sleep * (2**attempt))
    # should never reach
    raise last_err  # type: ignore[misc]


# ---------------------------
# Helpers
# ---------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _tier_from_name(name: str) -> int:
    m = TIER_RE.search(name or "")
    return int(m.group(1)) if m else 0


def _base_name(name: str) -> str:
    return re.sub(r"\s*\(T\d+\)\s*$", "", name or "").strip()


def _clamp(x: int, a: int, b: int) -> int:
    return max(a, min(b, x))


def _safe_json(v):
    if v is None:
        return []
    if isinstance(v, (list, dict)):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:
            return []
    return []


# ---------------------------
# Basic app state
# ---------------------------

def get_current_week(sb) -> int:
    # Try app_state(id=1) -> current_week, else app_settings.current_week, else 1
    try:
        r = _sb_execute(sb.table("app_state").select("current_week").eq("id", 1).single())
        if r.data and "current_week" in r.data:
            return int(r.data["current_week"])
    except Exception:
        pass

    try:
        r = _sb_execute(sb.table("app_settings").select("current_week").limit(1))
        if r.data:
            return int(r.data[0].get("current_week") or 1)
    except Exception:
        pass

    return 1


def list_players(sb) -> List[Dict[str, Any]]:
    r = _sb_execute(sb.table("players").select("id,name").order("name"))
    return r.data or []


def log(sb, player_id: str, kind: str, message: str, meta: Optional[Dict[str, Any]] = None) -> None:
    try:
        _sb_execute(sb.table("activity_log").insert({
            "player_id": player_id,
            "kind": kind,
            "message": message,
            "meta": meta or {},
        }))
    except Exception:
        # If activity_log schema differs, fail silently (but app keeps working)
        pass


def get_activity_log(sb, player_id: str, limit: int = 25) -> List[Dict[str, Any]]:
    try:
        r = _sb_execute(
            sb.table("activity_log")
            .select("created_at,message,kind,meta")
            .eq("player_id", player_id)
            .order("created_at", desc=True)
            .limit(limit)
        )
        return r.data or []
    except Exception:
        return []


# ---------------------------
# XP / Level / Tier
# ---------------------------

DEFAULT_TIER_UNLOCKS = [
    {"tier": 1, "unlocks_at_level": 1},
    {"tier": 2, "unlocks_at_level": 3},
    {"tier": 3, "unlocks_at_level": 6},
    {"tier": 4, "unlocks_at_level": 9},
    {"tier": 5, "unlocks_at_level": 13},
    {"tier": 6, "unlocks_at_level": 17},
    {"tier": 7, "unlocks_at_level": 20},
]

DEFAULT_XP_TABLE = {i: (i - 1) * 10 for i in range(1, 21)}  # level 2 at 10 xp, etc.


def _load_xp_table(sb) -> Dict[int, int]:
    try:
        r = sb.table("xp_table").select("level,xp_required").order("level").execute()
        if r.data:
            return {int(x["level"]): int(x["xp_required"]) for x in r.data}
    except Exception:
        pass
    return DEFAULT_XP_TABLE


def _load_tier_unlocks(sb) -> List[Dict[str, int]]:
    try:
        r = sb.table("tier_unlocks").select("tier,unlocks_at_level").order("tier").execute()
        if r.data:
            return [{"tier": int(x["tier"]), "unlocks_at_level": int(x["unlocks_at_level"])} for x in r.data]
    except Exception:
        pass
    return DEFAULT_TIER_UNLOCKS


def compute_level_from_xp(sb, total_xp: int) -> int:
    xp_table = _load_xp_table(sb)  # cumulative thresholds
    lvl = 1
    for k in sorted(xp_table.keys()):
        if total_xp >= xp_table[k]:
            lvl = k
    return _clamp(lvl, 1, 20)


def xp_required_for_level(sb, level: int) -> int:
    return int(_load_xp_table(sb).get(int(level), 0))


def max_tier_for_level(sb, level: int) -> int:
    tier = 1
    for row in _load_tier_unlocks(sb):
        if int(level) >= int(row["unlocks_at_level"]):
            tier = max(tier, int(row["tier"]))
    return tier


# ---------------------------
# Player Progress
# ---------------------------

def ensure_player_progress(sb, player_id: str) -> Dict[str, Any]:
    """
    player_progress supports:
      - player_id (uuid)
      - skills (jsonb)  -> {profession: {level:int, xp:int}}
      - known_recipes (jsonb array) optional
      - discovered_recipes (jsonb array) optional
    """
    try:
        r = sb.table("player_progress").select("player_id,skills,known_recipes,discovered_recipes").eq("player_id", player_id).execute()
        if r.data:
            row = r.data[0]
            row["skills"] = row.get("skills") or {}
            row["known_recipes"] = row.get("known_recipes") or []
            row["discovered_recipes"] = row.get("discovered_recipes") or row["known_recipes"]
            return row
    except Exception:
        pass

    # fallback schema without discovered_recipes
    try:
        r = sb.table("player_progress").select("player_id,skills,known_recipes").eq("player_id", player_id).execute()
        if r.data:
            row = r.data[0]
            row["skills"] = row.get("skills") or {}
            row["known_recipes"] = row.get("known_recipes") or []
            row["discovered_recipes"] = row["known_recipes"]
            return row
    except Exception:
        pass

    # create new
    base = {"player_id": player_id, "skills": {}, "known_recipes": [], "discovered_recipes": []}
    try:
        sb.table("player_progress").insert(base).execute()
    except Exception:
        sb.table("player_progress").insert({"player_id": player_id, "skills": {}, "known_recipes": []}).execute()
    return base


def list_professions_for_player(progress: Dict[str, Any]) -> List[str]:
    skills = progress.get("skills") or {}
    out = []
    for k, v in skills.items():
        if k and isinstance(v, dict):
            out.append(k)
    return sorted(out)


def set_skill_xp_delta(sb, player_id: str, profession: str, delta_xp: int) -> None:
    prog = ensure_player_progress(sb, player_id)
    skills = prog.get("skills") or {}

    s = skills.get(profession) or {"level": 1, "xp": 0}
    xp = max(0, int(s.get("xp", 0)) + int(delta_xp))
    lvl = compute_level_from_xp(sb, xp)

    s["xp"] = xp
    s["level"] = lvl
    skills[profession] = s

    sb.table("player_progress").update({"skills": skills}).eq("player_id", player_id).execute()
    log(sb, player_id, "xp", f"{profession}: XP {'+' if delta_xp >= 0 else ''}{delta_xp}", {"profession": profession, "delta": delta_xp})


# ---------------------------
# Inventory (hide zeros)
# ---------------------------

def list_inventory(sb, player_id: str) -> List[Dict[str, Any]]:
    r = sb.table("player_inventory").select("item_name,qty,quantity").eq("player_id", player_id).execute()
    rows = []
    for x in (r.data or []):
        q = x.get("quantity")
        if q is None:
            q = x.get("qty", 0)
        q = int(q or 0)
        if q <= 0:
            continue  # hide zero rows
        rows.append({"item_name": x["item_name"], "quantity": q})
    return rows


def inventory_adjust(sb, player_id: str, item_name: str, delta: int) -> None:
    inv = sb.table("player_inventory").select("qty,quantity").eq("player_id", player_id).eq("item_name", item_name).execute()
    cur = 0
    if inv.data:
        cur = inv.data[0].get("quantity")
        if cur is None:
            cur = inv.data[0].get("qty", 0)
        cur = int(cur or 0)

    new = max(0, cur + int(delta))

    if inv.data:
        sb.table("player_inventory").update({"qty": new, "quantity": new}).eq("player_id", player_id).eq("item_name", item_name).execute()
    else:
        if new > 0:
            sb.table("player_inventory").insert({"player_id": player_id, "item_name": item_name, "qty": new, "quantity": new}).execute()

    log(sb, player_id, "inventory", f"{item_name} {'+' if delta>=0 else ''}{delta}", {"item_name": item_name, "delta": delta})


def transfer_item(sb, from_player_id: str, to_player_id: str, item_name: str, qty: int) -> None:
    qty = int(qty)
    if qty <= 0:
        return

    inv = sb.table("player_inventory").select("qty,quantity").eq("player_id", from_player_id).eq("item_name", item_name).execute()
    if not inv.data:
        return

    cur = inv.data[0].get("quantity")
    if cur is None:
        cur = inv.data[0].get("qty", 0)
    cur = int(cur or 0)
    if cur <= 0:
        return

    qty = min(qty, cur)
    sb.table("player_inventory").update({"qty": cur - qty, "quantity": cur - qty}).eq("player_id", from_player_id).eq("item_name", item_name).execute()

    inv2 = sb.table("player_inventory").select("qty,quantity").eq("player_id", to_player_id).eq("item_name", item_name).execute()
    cur2 = 0
    if inv2.data:
        cur2 = inv2.data[0].get("quantity")
        if cur2 is None:
            cur2 = inv2.data[0].get("qty", 0)
        cur2 = int(cur2 or 0)

    if inv2.data:
        sb.table("player_inventory").update({"qty": cur2 + qty, "quantity": cur2 + qty}).eq("player_id", to_player_id).eq("item_name", item_name).execute()
    else:
        sb.table("player_inventory").insert({"player_id": to_player_id, "item_name": item_name, "qty": qty, "quantity": qty}).execute()

    log(sb, from_player_id, "transfer", f"Sent {qty} x {item_name}", {"to_player_id": to_player_id, "qty": qty})
    log(sb, to_player_id, "transfer", f"Received {qty} x {item_name}", {"from_player_id": from_player_id, "qty": qty})


# ---------------------------
# Gathering
# ---------------------------

def get_gather_professions(sb) -> List[str]:
    r = sb.table("gathering_items").select("profession").execute()
    return sorted({row["profession"] for row in (r.data or []) if row.get("profession")})


def dc_for_target_tier(unlocked_tier: int, target_tier: int) -> int:
    # DC10 for own tier, DC15 for +1, DC20 for +2
    if target_tier <= unlocked_tier:
        return 10
    if target_tier == unlocked_tier + 1:
        return 15
    return 20


def gathered_tier_from_roll(unlocked_tier: int, roll_total: int) -> Optional[int]:
    # close enough to test3 style: higher rolls push tier up (cap +2)
    if unlocked_tier == 1 and roll_total < 10:
        return None
    if roll_total >= 22:
        return unlocked_tier + 2
    if roll_total >= 18:
        return unlocked_tier + 1
    if roll_total >= 12:
        return unlocked_tier
    return max(1, unlocked_tier - 1)


def choose_random_gather_item(sb, profession: str, tier: int) -> Optional[Dict[str, Any]]:
    r = sb.table("gathering_items").select("name,description,use,profession,tier").eq("profession", profession).eq("tier", int(tier)).execute()
    items = r.data or []
    if not items:
        return None
    return random.choice(items)


def gathering_xp_for_item(item_name: str) -> int:
    # XP roughly = tier (simple)
    return max(1, _tier_from_name(item_name) or 1)


def roll_gathering_preview(sb, player_id: str, profession: str, roll_total: int) -> Dict[str, Any]:
    prog = ensure_player_progress(sb, player_id)
    skill = (prog.get("skills") or {}).get(profession) or {"level": 1, "xp": 0}
    level = int(skill.get("level", 1))
    unlocked = max_tier_for_level(sb, level)

    target = gathered_tier_from_roll(unlocked, int(roll_total))
    if target is None:
        return {"failed": True, "profession": profession, "roll_total": int(roll_total), "unlocked_tier": unlocked}

    target = _clamp(int(target), 1, unlocked + 2)
    dc = dc_for_target_tier(unlocked, target)

    found = choose_random_gather_item(sb, profession, target)
    if not found:
        return {"failed": True, "profession": profession, "roll_total": int(roll_total), "unlocked_tier": unlocked}

    xp_gain = gathering_xp_for_item(found.get("name", ""))

    return {
        "failed": False,
        "profession": profession,
        "roll_total": int(roll_total),
        "unlocked_tier": unlocked,
        "tier": int(target),
        "dc": int(dc),
        "item_name": found.get("name", ""),
        "description": found.get("description", "") or "",
        "use": found.get("use", "") or "",
        "xp_gain": int(xp_gain),
    }


def apply_gather_result(sb, player_id: str, preview: Dict[str, Any]) -> None:
    inventory_adjust(sb, player_id, preview["item_name"], +1)
    set_skill_xp_delta(sb, player_id, preview["profession"], int(preview.get("xp_gain", 1)))
    log(sb, player_id, "gather", f"Gathered {preview['item_name']}", preview)


# ---------------------------
# Recipes / Discovery
# ---------------------------

def list_all_recipes(sb) -> List[Dict[str, Any]]:
    r = sb.table("recipes").select(
        "name,profession,tier,rarity,category,craft_type,description,use,output_qty,base_price_gp,vendor_price_gp,sale_price_gp,components"
    ).execute()
    return r.data or []


def list_known_recipes_for_player(sb, player_id: str) -> List[str]:
    prog = ensure_player_progress(sb, player_id)
    known = prog.get("known_recipes") or prog.get("discovered_recipes") or []
    out = []
    seen = set()
    for x in known:
        if x not in seen:
            out.append(x)
            seen.add(x)
    return out


def _set_known_recipes(sb, player_id: str, known: List[str]) -> None:
    # store in both fields if present
    try:
        sb.table("player_progress").update({"known_recipes": known, "discovered_recipes": known}).eq("player_id", player_id).execute()
    except Exception:
        sb.table("player_progress").update({"known_recipes": known}).eq("player_id", player_id).execute()


def profession_allows_duplicate_components(sb, profession: str) -> bool:
    r = sb.table("recipes").select("components").eq("profession", profession).execute()
    for row in (r.data or []):
        comps = _safe_json(row.get("components"))
        names = [c.get("name") for c in comps if c.get("name")]
        if len(names) != len(set(names)):
            return True
    return False


def discovery_attempt_preview(sb, player_id: str, profession: str, item1: str, item2: str, item3: str, roll_total: int) -> Dict[str, Any]:
    chosen = [item1, item2, item3]
    chosen_base = sorted([_base_name(x) for x in chosen])

    recs = sb.table("recipes").select("name,tier,profession,components").eq("profession", profession).execute().data or []

    match = None
    best_overlap = 0
    best_recipe = None

    for r in recs:
        comps = _safe_json(r.get("components"))
        comp_names = sorted([_base_name(c.get("name", "")) for c in comps])
        overlap = len(set(chosen_base).intersection(set(comp_names)))
        if overlap > best_overlap:
            best_overlap = overlap
            best_recipe = r
        if comp_names == chosen_base:
            match = r
            break

    prog = ensure_player_progress(sb, player_id)
    skill = (prog.get("skills") or {}).get(profession) or {"level": 1, "xp": 0}
    level = int(skill.get("level", 1))
    unlocked = max_tier_for_level(sb, level)
    tier_cap = unlocked + 2

    learned_recipe = None
    outcome = "fail"
    hint = None

    if match:
        tier = int(match.get("tier", 1))
        if tier > tier_cap:
            outcome = "fail"
            hint = f"This recipe feels beyond your current mastery (cap T{tier_cap})."
        else:
            dc = dc_for_target_tier(unlocked, tier)
            if int(roll_total) >= dc:
                outcome = "success"
                learned_recipe = match["name"]
            else:
                outcome = "fail"
                hint = "The pattern is real, but the execution was lacking."
    else:
        if best_overlap >= 2 and int(roll_total) >= 18 and best_recipe:
            outcome = "partial_hint"
            comps = _safe_json(best_recipe.get("components"))
            comp_set = set([_base_name(c.get("name", "")) for c in comps])
            good = [x for x in chosen_base if x in comp_set]
            if len(good) >= 2:
                hint = f"Two components resonate together: **{good[0]}** and **{good[1]}**. The third is wrong."
            else:
                hint = "Some pieces feel close, but the pattern slips away."
        else:
            hint = "Nothing clicks. Maybe try a different combination."

    xp_gain = 3 if outcome == "success" else 1

    return {
        "profession": profession,
        "roll_total": int(roll_total),
        "items": chosen,
        "outcome": outcome,
        "hint": hint,
        "learned_recipe": learned_recipe,
        "xp_gain": int(xp_gain),
    }


def apply_discovery_attempt(sb, player_id: str, preview: Dict[str, Any]) -> None:
    # consume immediately
    for it in preview["items"]:
        inventory_adjust(sb, player_id, it, -1)

    set_skill_xp_delta(sb, player_id, preview["profession"], int(preview.get("xp_gain", 1)))

    if preview.get("learned_recipe"):
        known = list_known_recipes_for_player(sb, player_id)
        if preview["learned_recipe"] not in known:
            known.append(preview["learned_recipe"])
            _set_known_recipes(sb, player_id, known)
        log(sb, player_id, "discover", f"Discovered recipe: {preview['learned_recipe']}", preview)
    else:
        log(sb, player_id, "discover", f"Discovery attempt: {preview['outcome']}", preview)


# ---------------------------
# Crafting
# ---------------------------

def craft_preview(sb, player_id: str, recipe_name: str) -> Dict[str, Any]:
    r = sb.table("recipes").select("name,tier,profession,components,output_qty").eq("name", recipe_name).limit(1).execute()
    if not r.data:
        return {"can_craft": False, "missing": ["Recipe not found"], "tier": 1, "components": []}

    rec = r.data[0]
    comps = _safe_json(rec.get("components"))

    inv_map = {x["item_name"]: int(x["quantity"]) for x in list_inventory(sb, player_id)}

    missing = []
    for c in comps:
        nm = c.get("name")
        q = int(c.get("qty", 1))
        if inv_map.get(nm, 0) < q:
            missing.append(f"{nm} x{q} (have {inv_map.get(nm, 0)})")

    return {
        "recipe_name": recipe_name,
        "tier": int(rec.get("tier", 1)),
        "profession": rec.get("profession"),
        "components": comps,
        "output_qty": int(rec.get("output_qty", 1) or 1),
        "can_craft": len(missing) == 0,
        "missing": missing,
    }


def _craft_duration_seconds(tier: int) -> int:
    # your rule: T6 = 2 hours, others tier*10min
    if int(tier) == 6:
        return 2 * 60 * 60
    return int(tier) * 10 * 60


def start_craft_job(sb, player_id: str, preview: Dict[str, Any]) -> None:
    # consume components
    for c in preview["components"]:
        inventory_adjust(sb, player_id, c.get("name"), -int(c.get("qty", 1)))

    tier = int(preview.get("tier", 1))
    dur = _craft_duration_seconds(tier)
    ends = _now_utc() + timedelta(seconds=dur)

    payload = {
        "tier": tier,
        "profession": preview.get("profession"),
        "components": preview.get("components"),
        "output_qty": preview.get("output_qty", 1),
    }

    # IMPORTANT: match your existing schema:
    # id, player_id, job_type, ends_at, payload, done, created_at
    # plus (optional) status/kind/recipe_name/duration_seconds/started_at/completes_at/detail/result
    base_insert = {
        "player_id": player_id,
        "job_type": "craft",
        "ends_at": ends.isoformat(),
        "payload": payload,
        "done": False,
    }

    # Try insert with extended columns too (if available) but tolerate older caches
    try:
        sb.table("crafting_jobs").insert({
            **base_insert,
            "status": "active",
            "kind": "craft",
            "recipe_name": preview.get("recipe_name"),
            "duration_seconds": dur,
            "started_at": _now_utc().isoformat(),
            "completes_at": ends.isoformat(),
            "detail": {"tier": tier, "profession": preview.get("profession")},
            "result": {"output_qty": preview.get("output_qty", 1)},
        }).execute()
    except Exception:
        sb.table("crafting_jobs").insert(base_insert).execute()

    log(sb, player_id, "craft", f"Started crafting: {preview.get('recipe_name')}", {"tier": tier, "ends_at": ends.isoformat()})


def list_active_jobs(sb, player_id: str) -> List[Dict[str, Any]]:
    # active = not done; also support status='active' if used
    try:
        r = sb.table("crafting_jobs").select("*").eq("player_id", player_id).eq("done", False).order("created_at", desc=True).execute()
        return r.data or []
    except Exception:
        try:
            r = sb.table("crafting_jobs").select("*").eq("player_id", player_id).eq("status", "active").order("created_at", desc=True).execute()
            return r.data or []
        except Exception:
            return []


def claim_job_rewards(sb, player_id: str, job_id: str) -> None:
    job = sb.table("crafting_jobs").select("*").eq("id", job_id).single().execute().data
    if not job:
        return

    ends_at = job.get("ends_at") or job.get("completes_at")
    if not ends_at:
        return

    ends_dt = datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
    if _now_utc() < ends_dt:
        return

    payload = job.get("payload") or job.get("detail") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    recipe_name = job.get("recipe_name") or payload.get("recipe_name") or payload.get("name")
    output_qty = int(payload.get("output_qty", 1))

    if recipe_name:
        inventory_adjust(sb, player_id, recipe_name, +output_qty)
        prof = payload.get("profession")
        tier = int(payload.get("tier", 1))
        if prof:
            set_skill_xp_delta(sb, player_id, prof, max(1, tier + 1))
        log(sb, player_id, "craft", f"Craft completed: {recipe_name}", {"qty": output_qty})

    # mark done
    try:
        sb.table("crafting_jobs").update({"done": True, "status": "completed"}).eq("id", job_id).execute()
    except Exception:
        sb.table("crafting_jobs").update({"done": True}).eq("id", job_id).execute()


# ---------------------------
# Vendor
# ---------------------------

def _vendor_price_for_item(sb, item_name: str) -> float:
    r = sb.table("gathering_items").select("vendor_price_gp").eq("name", item_name).limit(1).execute()
    if r.data:
        try:
            return float(r.data[0].get("vendor_price_gp") or 0)
        except Exception:
            return 0.0
    return 0.0


def refresh_vendor_stock_for_player(sb, player_id: str, week: int, shop_profession: str) -> None:
    # pool = components used by recipes of that profession
    recs = sb.table("recipes").select("components").eq("profession", shop_profession).execute().data or []
    comp_names = set()
    for r in recs:
        comps = _safe_json(r.get("components"))
        for c in comps:
            nm = c.get("name")
            if nm:
                comp_names.add(nm)

    comp_names = list(comp_names)
    offers: List[Dict[str, Any]] = []

    # 20% chance of no offers
    if comp_names and random.random() >= 0.20:
        prog = ensure_player_progress(sb, player_id)
        skill = (prog.get("skills") or {}).get(shop_profession) or {"level": 1, "xp": 0}
        unlocked = max_tier_for_level(sb, int(skill.get("level", 1)))
        cap = unlocked + 2

        # 0–3 items per visit (we do 1–3 when offers happen)
        line_count = random.choices([1, 2, 3], weights=[50, 35, 15], k=1)[0]

        def pick_tier():
            # 50% tier X, 20% X+1, 10% X+2 (remaining 20% already used for "no offers")
            return random.choices([unlocked, unlocked + 1, unlocked + 2], weights=[50, 20, 10], k=1)[0]

        def pick_qty():
            return random.choices([1, 2, 3], weights=[50, 35, 15], k=1)[0]

        used = set()
        tries = 0
        while len(offers) < line_count and tries < 200:
            tries += 1
            nm = random.choice(comp_names)
            if nm in used:
                continue
            t = _tier_from_name(nm) or 1
            target_t = pick_tier()
            if t != target_t:
                continue
            if t > cap:
                continue
            used.add(nm)
            offers.append({
                "item_name": nm,
                "qty": pick_qty(),
                "price_gp": _vendor_price_for_item(sb, nm),
            })

    # upsert stock
    sb.table("vendor_stock").upsert({
        "player_id": player_id,
        "week": int(week),
        "shop_profession": shop_profession,
        "offers": offers
    }).execute()

    log(sb, player_id, "vendor", f"Vendor refreshed: {shop_profession} week {week}", {"offers": offers})


def get_vendor_stock(sb, player_id: str, week: int, shop_profession: str) -> Optional[Dict[str, Any]]:
    r = sb.table("vendor_stock").select("offers").eq("player_id", player_id).eq("week", int(week)).eq("shop_profession", shop_profession).limit(1).execute()
    return r.data[0] if r.data else None


def vendor_buy(sb, player_id: str, week: int, shop_profession: str, item_name: str, qty: int) -> None:
    qty = int(qty)
    if qty <= 0:
        return

    row = get_vendor_stock(sb, player_id, week, shop_profession)
    if not row:
        return

    offers = row.get("offers") or []
    new_offers = []
    bought = 0

    for o in offers:
        if o.get("item_name") == item_name and bought == 0:
            have = int(o.get("qty", 0))
            take = min(have, qty)
            if take > 0:
                inventory_adjust(sb, player_id, item_name, +take)
                bought = take
                remain = have - take
                if remain > 0:
                    o["qty"] = remain
                    new_offers.append(o)
            else:
                new_offers.append(o)
        else:
            new_offers.append(o)

    sb.table("vendor_stock").update({"offers": new_offers}).eq("player_id", player_id).eq("week", int(week)).eq("shop_profession", shop_profession).execute()

    if bought:
        log(sb, player_id, "vendor", f"Bought {bought} x {item_name}", {"qty": bought})
