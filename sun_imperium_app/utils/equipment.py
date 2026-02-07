from __future__ import annotations

from typing import Any, Dict, List


def get_equipment_items(sb, category: str) -> List[Dict[str, Any]]:
    """List equipment items available for a given mission category.

    category: 'diplomacy' | 'intelligence'
    """
    return (
        sb.table("mission_equipment")
        .select("id,name,category,cost,success_bonus_pct,description")
        .eq("category", category)
        .order("cost")
        .execute()
        .data
        or []
    )


def get_equipment_inventory(sb, category: str) -> Dict[str, int]:
    """Return a mapping equipment_id -> quantity owned."""
    rows = (
        sb.table("equipment_inventory")
        .select("equipment_id,quantity")
        .eq("category", category)
        .execute()
        .data
        or []
    )
    return {r["equipment_id"]: int(r.get("quantity") or 0) for r in rows}


def add_equipment(sb, *, category: str, equipment_id: str, delta: int) -> None:
    """Increment equipment inventory."""
    if delta == 0:
        return
    inv = (
        sb.table("equipment_inventory")
        .select("id,quantity")
        .eq("category", category)
        .eq("equipment_id", equipment_id)
        .limit(1)
        .execute()
        .data
    )
    if inv:
        row = inv[0]
        qty = int(row.get("quantity") or 0) + int(delta)
        if qty < 0:
            qty = 0
        sb.table("equipment_inventory").update({"quantity": qty}).eq("id", row["id"]).execute()
    else:
        sb.table("equipment_inventory").insert(
            {"category": category, "equipment_id": equipment_id, "quantity": int(max(delta, 0))}
        ).execute()


def compute_equipment_bonus_pct(
    equipment_rows: List[Dict[str, Any]],
    assignment: Dict[str, int],
) -> float:
    """Compute total bonus percentage from an equipment assignment.

    assignment: equipment_id -> quantity assigned
    """
    by_id = {e["id"]: e for e in equipment_rows}
    total = 0.0
    for eid, qty in (assignment or {}).items():
        if qty <= 0:
            continue
        item = by_id.get(eid)
        if not item:
            continue
        bonus = float(item.get("success_bonus_pct") or 0.0)
        total += bonus * int(qty)
    return total
