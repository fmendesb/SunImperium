"""Squad DB helpers.

This project has seen multiple Supabase schemas while iterating.
In particular, `squad_members` exists in at least these variants:

1) (id, squad_id, unit_id, unit_type, quantity)
2) (id, squad_id, unit_id, quantity)
3) (id, squad_id, unit_type, quantity)

PostgREST raises an APIError when selecting/filtering on missing columns.
These helpers provide best-effort reads/writes that tolerate those variants.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Tuple


def _try_select(sb, *, cols: str, squad_id: str) -> list[dict]:
    return (
        sb.table("squad_members")
        .select(cols)
        .eq("squad_id", squad_id)
        .execute()
        .data
        or []
    )


def fetch_members(sb, squad_id: str, unit_type_by_id: Optional[Dict[str, str]] = None) -> Tuple[list[dict], Dict[str, bool]]:
    """Fetch squad members and normalize keys.

    Returns (rows, capabilities)
      rows: list of dicts with keys: id, quantity, unit_id (optional), unit_type (optional)
      capabilities: {"has_unit_id": bool, "has_unit_type": bool}
    """

    # Try richest -> weakest.
    try:
        rows = _try_select(sb, cols="id,unit_id,unit_type,quantity", squad_id=squad_id)
        caps = {"has_unit_id": True, "has_unit_type": True}
    except Exception:
        try:
            rows = _try_select(sb, cols="id,unit_id,quantity", squad_id=squad_id)
            caps = {"has_unit_id": True, "has_unit_type": False}
        except Exception:
            rows = _try_select(sb, cols="id,unit_type,quantity", squad_id=squad_id)
            caps = {"has_unit_id": False, "has_unit_type": True}

    # Normalize.
    unit_type_by_id = unit_type_by_id or {}
    for r in rows:
        r["quantity"] = int(r.get("quantity") or 0)
        if not r.get("unit_type"):
            uid = r.get("unit_id")
            if uid and uid in unit_type_by_id:
                r["unit_type"] = unit_type_by_id[uid]
        if r.get("unit_type") is None:
            r["unit_type"] = "Other"

    return rows, caps


def upsert_member(
    sb,
    *,
    squad_id: str,
    qty_delta: int,
    unit_id: Optional[str] = None,
    unit_type: Optional[str] = None,
) -> None:
    """Best-effort increment of a member row.

    - If unit_id column exists, use (squad_id, unit_id) as the identity.
    - Else, use (squad_id, unit_type).
    """

    qty_delta = int(qty_delta or 0)
    if qty_delta <= 0:
        return

    # Detect which key we can use by trying a tiny query.
    has_unit_id = True
    try:
        sb.table("squad_members").select("unit_id").limit(1).execute()
    except Exception:
        has_unit_id = False

    has_unit_type = True
    try:
        sb.table("squad_members").select("unit_type").limit(1).execute()
    except Exception:
        has_unit_type = False

    # Prefer unit_id if available.
    if has_unit_id and unit_id:
        q = (
            sb.table("squad_members")
            .select("id,quantity")
            .eq("squad_id", squad_id)
            .eq("unit_id", unit_id)
            .limit(1)
            .execute()
            .data
        )
        if q:
            sb.table("squad_members").update({"quantity": int(q[0]["quantity"]) + qty_delta}).eq("id", q[0]["id"]).execute()
            return

        payload: Dict[str, Any] = {"squad_id": squad_id, "unit_id": unit_id, "quantity": qty_delta}
        if has_unit_type:
            payload["unit_type"] = unit_type or "Other"
        sb.table("squad_members").insert(payload).execute()
        return

    # Fallback: unit_type identity.
    if has_unit_type:
        ut = (unit_type or "Other")
        q = (
            sb.table("squad_members")
            .select("id,quantity")
            .eq("squad_id", squad_id)
            .eq("unit_type", ut)
            .limit(1)
            .execute()
            .data
        )
        if q:
            sb.table("squad_members").update({"quantity": int(q[0]["quantity"]) + qty_delta}).eq("id", q[0]["id"]).execute()
            return
        sb.table("squad_members").insert({"squad_id": squad_id, "unit_type": ut, "quantity": qty_delta}).execute()
        return

    # No workable schema.
    raise RuntimeError("squad_members table is missing both unit_id and unit_type columns")
