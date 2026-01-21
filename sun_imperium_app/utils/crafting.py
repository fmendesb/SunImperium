from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from supabase import Client


# ----------------------------
# Helpers
# ----------------------------

def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


# ----------------------------
# Reads
# ----------------------------

def list_players(sb: Client) -> List[dict]:
    res = sb.table("players").select("id,name").order("name").execute()
    return res.data or []


def get_player_progress(sb: Client, player_id: str) -> dict:
    res = sb.table("player_progress").select("skills,discovered_recipes").eq("player_id", player_id).limit(1).execute()
    if not res.data:
        return {"skills": {}, "discovered_recipes": []}
    row = res.data[0]
    return {"skills": row.get("skills") or {}, "discovered_recipes": row.get("discovered_recipes") or []}


def list_inventory(sb: Client, player_id: str) -> List[dict]:
    res = sb.table("player_inventory").select("item_name,quantity").eq("player_id", player_id).order("item_name").execute()
    return res.data or []


def inventory_map(sb: Client, player_id: str) -> Dict[str, int]:
    inv = list_inventory(sb, player_id)
    return {r["item_name"]: int(r.get("quantity") or 0) for r in inv}


def list_gathering_items(sb: Client, *, profession: Optional[str] = None, max_tier: Optional[int] = None) -> List[dict]:
    q = sb.table("gathering_items").select(
        "profession,tier,rarity,name,is_special,description,use,base_price_gp,vendor_price_gp,sale_price_gp,region,family"
    )
    if profession:
        q = q.eq("profession", profession)
    if max_tier is not None:
        q = q.lte("tier", max_tier)
    res = q.order("tier").order("name").execute()
    return res.data or []


def list_recipes(sb: Client, *, profession: Optional[str] = None, max_tier: Optional[int] = None) -> List[dict]:
    q = sb.table("recipes").select(
        "profession,secondary_profession,tier,rarity,name,category,craft_type,description,use,output_qty,base_price_gp,vendor_price_gp,sale_price_gp,components"
    )
    if profession:
        q = q.eq("profession", profession)
    if max_tier is not None:
        q = q.lte("tier", max_tier)
    res = q.order("tier").order("name").execute()
    return res.data or []


def get_current_week(sb: Client) -> int:
    res = sb.table("app_state").select("current_week").eq("id", 1).limit(1).execute()
    if res.data:
        return int(res.data[0].get("current_week") or 1)
    return 1


def list_jobs(sb: Client, player_id: str, *, status: Optional[str] = None) -> List[dict]:
    q = sb.table("crafting_jobs").select(
        "id,kind,status,item_name,recipe_name,detail,started_at,duration_seconds,completes_at,result,created_at"
    ).eq("player_id", player_id)
    if status:
        q = q.eq("status", status)
    res = q.order("created_at", desc=True).execute()
    return res.data or []


def list_activity(sb: Client, player_id: str, limit: int = 50) -> List[dict]:
    res = (
        sb.table("activity_log")
        .select("created_at,action,message,meta")
        .eq("player_id", player_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


# ----------------------------
# Progression rules (simple, adjustable later)
# ----------------------------

def unlocked_max_tier_for_skill(level: int) -> int:
    """
    Simple rule for now:
    level 1 => tier 1
    level 2 => tier 2
    ...
    level 7 => tier 7
    """
    return max(1, min(7, int(level)))


def get_professions_from_skills(skills: dict) -> List[str]:
    return sorted([k for k, v in (skills or {}).items() if isinstance(v, dict) and v.get("level") is not None])


def get_skill_level(skills: dict, profession: str) -> int:
    v = (skills or {}).get(profession) or {}
    try:
        return int(v.get("level") or 1)
    except Exception:
        return 1


# ----------------------------
# Inventory mutation
# ----------------------------

def add_inventory(sb: Client, *, player_id: str, item_name: str, delta: int) -> None:
    if delta == 0:
        return
    # Upsert by (player_id,item_name)
    # Read current
    res = (
        sb.table("player_inventory")
        .select("quantity")
        .eq("player_id", player_id)
        .eq("item_name", item_name)
        .limit(1)
        .execute()
    )
    cur = int(res.data[0]["quantity"]) if res.data else 0
    nxt = cur + int(delta)
    if nxt < 0:
        raise ValueError(f"Not enough '{item_name}' (have {cur}, need {abs(delta)}).")
    if res.data:
        sb.table("player_inventory").update({"quantity": nxt}).eq("player_id", player_id).eq("item_name", item_name).execute()
    else:
        sb.table("player_inventory").insert({"player_id": player_id, "item_name": item_name, "quantity": nxt}).execute()


# ----------------------------
# Logs + Undo
# ----------------------------

def push_undo(sb: Client, *, player_id: str, category: str, payload: dict) -> None:
    sb.table("undo_actions").insert({"player_id": player_id, "category": category, "payload": payload}).execute()


def pop_latest_undo(sb: Client, *, player_id: str, category: str) -> Optional[dict]:
    res = (
        sb.table("undo_actions")
        .select("id,payload,created_at")
        .eq("player_id", player_id)
        .eq("category", category)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def delete_undo(sb: Client, undo_id: str) -> None:
    sb.table("undo_actions").delete().eq("id", undo_id).execute()


def log(sb: Client, *, player_id: str, action: str, message: str, meta: Optional[dict] = None) -> None:
    week = None
    try:
        week = get_current_week(sb)
    except Exception:
        week = None
    sb.table("activity_log").insert(
        {"player_id": player_id, "week": week, "action": action, "message": message, "meta": meta or {}}
    ).execute()


# ----------------------------
# Timers
# ----------------------------

def duration_seconds_for_tier(tier: int, *, kind: str) -> int:
    """
    Mirrors your expectation:
    Tier 6 => 2 hours.
    Everything else can be tuned later.
    """
    tier = int(tier)
    if tier == 6:
        return 2 * 60 * 60
    # baseline ladder (lightweight)
    # T1: 2m, T2: 5m, T3: 10m, T4: 20m, T5: 40m, T7: 4h
    if tier == 1:
        return 2 * 60
    if tier == 2:
        return 5 * 60
    if tier == 3:
        return 10 * 60
    if tier == 4:
        return 20 * 60
    if tier == 5:
        return 40 * 60
    if tier >= 7:
        return 4 * 60 * 60
    return 10 * 60


def start_job(
    sb: Client,
    *,
    player_id: str,
    kind: str,
    tier: int,
    item_name: Optional[str] = None,
    recipe_name: Optional[str] = None,
    detail: Optional[dict] = None,
    result: Optional[dict] = None,
) -> dict:
    dur = duration_seconds_for_tier(tier, kind=kind)
    started = utcnow()
    completes = started + timedelta(seconds=dur)
    row = {
        "player_id": player_id,
        "kind": kind,
        "status": "active",
        "item_name": item_name,
        "recipe_name": recipe_name,
        "detail": detail or {},
        "started_at": started.isoformat(),
        "duration_seconds": dur,
        "completes_at": completes.isoformat(),
        "result": result or {},
    }
    res = sb.table("crafting_jobs").insert(row).execute()
    return (res.data or [row])[0]


def mark_job_completed(sb: Client, job_id: str) -> None:
    sb.table("crafting_jobs").update({"status": "completed"}).eq("id", job_id).execute()


def cancel_job(sb: Client, job_id: str) -> None:
    sb.table("crafting_jobs").update({"status": "cancelled"}).eq("id", job_id).execute()


# ----------------------------
# Gather
# ----------------------------

def start_gather(sb: Client, *, player_id: str, item: dict, qty: int = 1) -> None:
    qty = int(qty)
    if qty <= 0:
        raise ValueError("Quantity must be >= 1.")
    tier = int(item["tier"])
    name = item["name"]
    # Job result: add item qty on claim
    job = start_job(
        sb,
        player_id=player_id,
        kind="gather",
        tier=tier,
        item_name=name,
        detail={"tier": tier, "profession": item.get("profession"), "qty": qty},
        result={"add_inventory": [{"name": name, "qty": qty}]},
    )
    push_undo(sb, player_id=player_id, category="gather", payload={"job_id": job.get("id")})
    log(sb, player_id=player_id, action="started_gather", message=f"Started gathering: {name} x{qty}.", meta={"item": name, "qty": qty})


def claim_job_rewards(sb: Client, *, player_id: str, job: dict) -> None:
    # Apply result payload into inventory
    result = job.get("result") or {}
    adds = result.get("add_inventory") or []
    for entry in adds:
        add_inventory(sb, player_id=player_id, item_name=entry["name"], delta=int(entry["qty"]))
    # mark completed (idempotent)
    if job.get("status") != "completed":
        mark_job_completed(sb, job["id"])
    log(sb, player_id=player_id, action="claimed", message=f"Claimed rewards for job.", meta={"job_id": job["id"], "kind": job.get("kind")})


# ----------------------------
# Craft
# ----------------------------

def can_craft(inv: Dict[str, int], components: List[dict], qty: int = 1) -> Tuple[bool, List[str]]:
    missing = []
    for c in components or []:
        name = c.get("name")
        need = int(c.get("qty") or 0) * int(qty)
        have = int(inv.get(name, 0))
        if have < need:
            missing.append(f"{name}: need {need}, have {have}")
    return (len(missing) == 0), missing


def start_craft(sb: Client, *, player_id: str, recipe: dict, qty: int = 1) -> None:
    qty = int(qty)
    if qty <= 0:
        raise ValueError("Quantity must be >= 1.")
    name = recipe["name"]
    tier = int(recipe["tier"])
    output_qty = int(recipe.get("output_qty") or 1) * qty
    components = recipe.get("components") or []
    inv = inventory_map(sb, player_id)

    ok, missing = can_craft(inv, components, qty=qty)
    if not ok:
        raise ValueError("Missing components:\n" + "\n".join(missing))

    # Consume components upfront (matches common crafting UX)
    for c in components:
        comp_name = c["name"]
        need = int(c.get("qty") or 0) * qty
        add_inventory(sb, player_id=player_id, item_name=comp_name, delta=-need)

    job = start_job(
        sb,
        player_id=player_id,
        kind="craft",
        tier=tier,
        recipe_name=name,
        detail={"tier": tier, "profession": recipe.get("profession"), "qty": qty},
        result={"add_inventory": [{"name": name, "qty": output_qty}]},
    )

    push_undo(
        sb,
        player_id=player_id,
        category="craft",
        payload={
            "job_id": job.get("id"),
            "refund_components": [{"name": c["name"], "qty": int(c.get("qty") or 0) * qty} for c in components],
        },
    )
    log(sb, player_id=player_id, action="started_craft", message=f"Started crafting: {name} (x{qty}).", meta={"recipe": name, "qty": qty})


def undo_last(sb: Client, *, player_id: str, category: str) -> bool:
    undo = pop_latest_undo(sb, player_id=player_id, category=category)
    if not undo:
        return False
    payload = undo.get("payload") or {}
    # Basic undo behavior:
    # - If payload contains job_id: cancel job (and optionally refund components)
    job_id = payload.get("job_id")
    if job_id:
        # cancel job
        cancel_job(sb, job_id)
    for r in payload.get("refund_components") or []:
        add_inventory(sb, player_id=player_id, item_name=r["name"], delta=int(r["qty"]))
    delete_undo(sb, undo["id"])
    log(sb, player_id=player_id, action="undo", message=f"Undid last {category} action.", meta={"category": category})
    return True
