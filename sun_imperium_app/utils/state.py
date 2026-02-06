from __future__ import annotations

from datetime import datetime, timezone
from supabase import Client


def ensure_bootstrap(sb: Client) -> None:
    """Ensures minimum rows exist so the app can run.

    This project evolved over time; some older branches used `app_settings` and
    `weeks.status`. The current canonical tables are:
      - app_state(id smallint, current_week int, updated_at timestamptz)
      - weeks(week int pk, opened_at timestamptz, closed_at timestamptz, note text)

    This function only ensures these canonical tables have the minimum rows.
    """

    # app_state singleton row
    r = sb.table("app_state").select("id,current_week").order("id").limit(1).execute()
    if not r.data:
        sb.table("app_state").insert({"id": 1, "current_week": 1, "updated_at": _now()}).execute()

    current_week = int(sb.table("app_state").select("current_week").eq("id", 1).execute().data[0]["current_week"])

    # Ensure weeks row exists
    wk = sb.table("weeks").select("week").eq("week", current_week).execute()
    if not wk.data:
        sb.table("weeks").insert({"week": current_week, "opened_at": _now(), "note": "auto-seeded"}).execute()

    # Ensure ledger has at least one row so dashboards don't crash
    led = sb.table("ledger_entries").select("id").limit(1).execute()
    if not led.data:
        sb.table("ledger_entries").insert(
            {
                "week": current_week,
                "direction": "in",
                "amount": 0,
                "category": "bootstrap",
                "note": "Bootstrap entry",
                "metadata": {},
            }
        ).execute()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
