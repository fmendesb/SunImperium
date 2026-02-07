from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional


def log_activity(
    sb,
    *,
    kind: str,
    message: str,
    meta: Optional[Dict[str, Any]] = None,
    player_id: Optional[str] = None,
):
    """Write a row to activity_log if available.

    This is intentionally best-effort: logging should never break gameplay.
    """

    try:
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "message": message,
            "meta": meta or {},
            "player_id": player_id,
        }
        # Some schemas may not include created_at/player_id; Supabase will ignore unknown keys.
        sb.table("activity_log").insert(payload).execute()
    except Exception:
        return
