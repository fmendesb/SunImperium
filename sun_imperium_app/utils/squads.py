"""Squad helpers (schema-tolerant).

This app has been deployed against multiple Supabase schema variants for
`squad_members`. In particular, some DBs:

- store unit membership by unit_id
- others store by unit_type
- some have both
- some have no surrogate `id` column

PostgREST fails hard when selecting/filtering a missing column, so these
helpers probe capabilities and then use only safe column sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class SquadMemberCaps:
    has_unit_id: bool
    has_unit_type: bool


def _safe_exec(q):
    """Execute a postgrest query and return data list (or raise)."""
    return (q.execute().data or [])


def detect_member_caps(sb) -> SquadMemberCaps:
    """Detect whether squad_members has unit_id and/or unit_type columns."""
    # Try selecting unit_id
    has_unit_id = True
    try:
        _safe_exec(sb.table("squad_members").select("unit_id").limit(1))
    except Exception:
        has_unit_id = False

    has_unit_type = True
    try:
        _safe_exec(sb.table("squad_members").select("unit_type").limit(1))
    except Exception:
        has_unit_type = False

    return SquadMemberCaps(has_unit_id=has_unit_id, has_unit_type=has_unit_type)


def fetch_members(
    sb,
    squad_id,
    unit_type_by_id: Optional[Dict[Any, str]] = None,
    _caps: Optional[SquadMemberCaps] = None,
) -> Tuple[List[Dict[str, Any]], SquadMemberCaps]:
    """Fetch members for squad_id.

    Returns rows normalized to always include: unit_id (optional), unit_type (optional), quantity.
    Never assumes an `id` column exists.
    """
    caps = _caps or detect_member_caps(sb)

    if caps.has_unit_id and caps.has_unit_type:
        rows = _safe_exec(
            sb.table("squad_members")
            .select("unit_id,unit_type,quantity")
            .eq("squad_id", squad_id)
        )
    elif caps.has_unit_id:
        rows = _safe_exec(
            sb.table("squad_members")
            .select("unit_id,quantity")
            .eq("squad_id", squad_id)
        )
    elif caps.has_unit_type:
        rows = _safe_exec(
            sb.table("squad_members")
            .select("unit_type,quantity")
            .eq("squad_id", squad_id)
        )
    else:
        # extremely broken schema, but don't crash UI
        rows = []

    # normalize
    for r in rows:
        r["quantity"] = int(r.get("quantity") or 0)
        if "unit_type" not in r or not r.get("unit_type"):
            if unit_type_by_id and r.get("unit_id") in unit_type_by_id:
                r["unit_type"] = unit_type_by_id.get(r.get("unit_id")) or "Other"
        if r.get("unit_type") is None:
            r["unit_type"] = "Other"

    return rows, caps


def upsert_member_quantity(
    sb,
    squad_id,
    quantity: int,
    caps: SquadMemberCaps,
    *,
    unit_id: Any = None,
    unit_type: Optional[str] = None,
) -> None:
    """Set quantity for a single member key.

    Uses (squad_id, unit_id) when available, else (squad_id, unit_type).
    Never uses id.
    """
    quantity = int(quantity)
    if quantity < 0:
        quantity = 0

    if caps.has_unit_id and unit_id is not None:
        # update existing
        existing = _safe_exec(
            sb.table("squad_members")
            .select("quantity")
            .eq("squad_id", squad_id)
            .eq("unit_id", unit_id)
            .limit(1)
        )
        if existing:
            sb.table("squad_members").update({"quantity": quantity}).eq("squad_id", squad_id).eq("unit_id", unit_id).execute()
        else:
            payload: Dict[str, Any] = {"squad_id": squad_id, "unit_id": unit_id, "quantity": quantity}
            if caps.has_unit_type and unit_type:
                payload["unit_type"] = unit_type
            sb.table("squad_members").insert(payload).execute()
        return

    if caps.has_unit_type and unit_type:
        existing = _safe_exec(
            sb.table("squad_members")
            .select("quantity")
            .eq("squad_id", squad_id)
            .eq("unit_type", unit_type)
            .limit(1)
        )
        if existing:
            sb.table("squad_members").update({"quantity": quantity}).eq("squad_id", squad_id).eq("unit_type", unit_type).execute()
        else:
            payload2: Dict[str, Any] = {"squad_id": squad_id, "unit_type": unit_type, "quantity": quantity}
            sb.table("squad_members").insert(payload2).execute()
        return


def add_member_quantity(
    sb,
    squad_id,
    add_qty: int,
    caps: SquadMemberCaps,
    *,
    unit_id: Any = None,
    unit_type: Optional[str] = None,
) -> None:
    """Increase member quantity by add_qty (creates row if missing)."""
    add_qty = int(add_qty)
    if add_qty <= 0:
        return

    if caps.has_unit_id and unit_id is not None:
        existing = _safe_exec(
            sb.table("squad_members")
            .select("quantity")
            .eq("squad_id", squad_id)
            .eq("unit_id", unit_id)
            .limit(1)
        )
        cur = int(existing[0]["quantity"]) if existing else 0
        upsert_member_quantity(sb, squad_id, cur + add_qty, caps, unit_id=unit_id, unit_type=unit_type)
        return

    if caps.has_unit_type and unit_type:
        existing = _safe_exec(
            sb.table("squad_members")
            .select("quantity")
            .eq("squad_id", squad_id)
            .eq("unit_type", unit_type)
            .limit(1)
        )
        cur = int(existing[0]["quantity"]) if existing else 0
        upsert_member_quantity(sb, squad_id, cur + add_qty, caps, unit_type=unit_type)
        return


def bulk_add_members(
    sb,
    squad_id,
    adds: List[Dict[str, Any]],
    caps: SquadMemberCaps,
) -> None:
    """Bulk add quantities.

    Each item in adds: {unit_id?, unit_type?, qty}
    """
    for a in adds:
        qty = int(a.get("qty") or 0)
        if qty <= 0:
            continue
        add_member_quantity(
            sb,
            squad_id,
            qty,
            caps,
            unit_id=a.get("unit_id"),
            unit_type=a.get("unit_type"),
        )
