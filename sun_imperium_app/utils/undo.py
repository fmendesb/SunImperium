from __future__ import annotations

import json
from supabase import Client


def log_action(sb: Client, *, category: str, action: str, payload: dict) -> None:
    sb.table("action_logs").insert(
        {
            "category": category,
            "action": action,
            "payload": payload,
        }
    ).execute()


def get_last_action(sb: Client, *, category: str) -> dict | None:
    res = (
        sb.table("action_logs")
        .select("id,action,payload,created_at")
        .eq("category", category)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None
    return res.data[0]


def pop_last_action(sb: Client, *, action_id: str) -> None:
    sb.table("action_logs").delete().eq("id", action_id).execute()
