"""Squad DB helpers.

This project has seen multiple Supabase schemas while iterating.
In particular, `squad_members` exists in at least these variants:

1) (id, squad_id, unit_id, unit_type, quantity)
2) (id, squad_id, unit_id, quantity)
3) (id, squad_id, unit_type, quantity)
4) (squad_id, unit_id, unit_type, quantity)   # no id
5) (squad_id, unit_id, quantity)
6) (squad_id, unit_type, quantity)

PostgREST raises an APIError when selecting/filtering on missing columns.
These helpers provide best-effort reads/writes that tolerate those variants.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


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
      rows: list of dicts with keys: quantity, unit_id (optional), unit_type (optional), _key (synthetic)
      capabilities: {"has_unit_id": bool, "has_unit_type": bool, "has_id": bool}
    """

    # NOTE: Some deployed schemas do not have a surrogate `id` column at all.
    # Also, PostgREST column existence detection can behave oddly under RLS/empty tables.
    # To be maximally compatible, we NEVER select or rely on `id`.
    has_id = False

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

    # Try richest -> weakest, WITHOUT assuming `id` exists.
    base_cols = []
    if has_unit_id:
        base_cols.append("unit_id")
    if has_unit_type:
        base_cols.append("unit_type")
    base_cols.append("quantity")

    # Some schemas might not support selecting all present cols at once (rare), so try fallbacks.
    rows: list[dict]
    try:
        rows = _try_select(sb, cols=",".join(base_cols), squad_id=squad_id)
    except Exception:
        # progressively drop columns
        cols_try = [c for c in base_cols if c != "unit_type"]
        try:
            rows = _try_select(sb, cols=",".join(cols_try), squad_id=squad_id)
            has_unit_type = False
        except Exception:
            cols_try = [c for c in base_cols if c != "unit_id"]
            rows = _try_select(sb, cols=",".join(cols_try), squad_id=squad_id)
            has_unit_id = False

    caps = {"has_unit_id": has_unit_id, "has_unit_type": has_unit_type, "has_id": False}

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

        # Provide a stable synthetic key for UI/data-editor rows.
        if r.get("unit_id"):
            r["_key"] = f"{squad_id}|uid|{r.get('unit_id')}"
        else:
            r["_key"] = f"{squad_id}|ut|{r.get('unit_type')}"

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

    # We NEVER rely on an `id` column. Some schemas don't have it.
    has_id = False

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
            .select("quantity")
            .eq("squad_id", squad_id)
            .eq("unit_id", unit_id)
            .limit(1)
            .execute()
            .data
        )
        if q:
            new_qty = int(q[0].get("quantity") or 0) + qty_delta
            sb.table("squad_members").update({"quantity": new_qty}).eq("squad_id", squad_id).eq("unit_id", unit_id).execute()
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
            .select("quantity")
            .eq("squad_id", squad_id)
            .eq("unit_type", ut)
            .limit(1)
            .execute()
            .data
        )
        if q:
            new_qty = int(q[0].get("quantity") or 0) + qty_delta
            sb.table("squad_members").update({"quantity": new_qty}).eq("squad_id", squad_id).eq("unit_type", ut).execute()
            return
        sb.table("squad_members").insert({"squad_id": squad_id, "unit_type": ut, "quantity": qty_delta}).execute()
        return

    # No workable schema.
    raise RuntimeError("squad_members table is missing both unit_id and unit_type columns")
