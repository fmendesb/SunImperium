from __future__ import annotations

from supabase import Client


def ensure_bootstrap(sb: Client) -> None:
    """Ensures minimum rows exist so the app can run."""
    # app_settings single row
    res = sb.table("app_settings").select("id,current_week").limit(1).execute()
    if not res.data:
        sb.table("app_settings").insert({"current_week": 1, "gold_starting": 0}).execute()

    settings = sb.table("app_settings").select("current_week").limit(1).execute().data[0]
    week = int(settings["current_week"])
    # ensure weeks row exists
    wk = sb.table("weeks").select("week").eq("week", week).execute()
    if not wk.data:
        sb.table("weeks").insert({"week": week, "status": "open"}).execute()

    # ensure ledger has opening balance entry if empty
    led = sb.table("ledger_entries").select("id").limit(1).execute()
    if not led.data:
        # opening balance = gold_starting
        gs = float(settings.get("gold_starting", 0) or 0)
        if gs != 0:
            sb.table("ledger_entries").insert(
                {
                    "week": week,
                    "direction": "in",
                    "amount": gs,
                    "category": "opening_balance",
                    "note": "Opening balance",
                }
            ).execute()
