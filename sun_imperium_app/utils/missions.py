from __future__ import annotations

import hashlib
import random
from typing import Any, Dict, List, Optional


def _stable_d100(seed_key: str) -> int:
    """Deterministic d100 roll based on seed_key.

    Used so the same mission resolution is reproducible once recorded.
    """
    h = hashlib.sha256(seed_key.encode("utf-8")).hexdigest()
    seed = int(h[:8], 16)
    rng = random.Random(seed)
    return rng.randint(1, 100)


def list_missions(sb, table: str, week: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    q = sb.table(table).select(
        "id,week,unit_id,quantity,target,objective,status,created_at,eta_week,base_success,bonus_success,total_success,roll,success,resolution_note,equipment_assignment"
    ).eq("week", week).order("created_at", desc=True)
    if status:
        q = q.eq("status", status)
    return q.execute().data or []


def create_mission(
    sb,
    *,
    table: str,
    week: int,
    unit_id: str,
    quantity: int,
    target: str,
    objective: str,
    base_success: float,
    bonus_success: float,
    eta_week: Optional[int] = None,
    equipment_assignment: Optional[Dict[str, int]] = None,
):
    total_success = max(0.0, min(95.0, base_success + bonus_success))
    sb.table(table).insert(
        {
            "week": int(week),
            "unit_id": unit_id,
            "quantity": int(max(quantity, 1)),
            "target": target,
            "objective": objective,
            "status": "active",
            "eta_week": int(eta_week) if eta_week is not None else None,
            "base_success": float(base_success),
            "bonus_success": float(bonus_success),
            "total_success": float(total_success),
            "equipment_assignment": equipment_assignment or {},
        }
    ).execute()


def resolve_mission(
    sb,
    *,
    table: str,
    mission_id: str,
    dm_note: str = "",
    seed_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Resolve a mission.

    If already resolved, returns the existing row.
    """
    row = (
        sb.table(table)
        .select("id,total_success,roll,success,status")
        .eq("id", mission_id)
        .limit(1)
        .execute()
        .data
    )
    if not row:
        raise ValueError("Mission not found")
    row = row[0]
    if str(row.get("status")) == "resolved":
        return row

    total = float(row.get("total_success") or 0.0)
    seed = seed_key or f"{mission_id}:{total}"
    roll = int(_stable_d100(seed))
    success = bool(roll <= total)

    sb.table(table).update(
        {
            "status": "resolved",
            "roll": roll,
            "success": success,
            "resolution_note": dm_note,
        }
    ).eq("id", mission_id).execute()

    return {"id": mission_id, "roll": roll, "success": success, "total_success": total}
