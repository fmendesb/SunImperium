from dataclasses import dataclass
from typing import Any, Dict, Optional

from supabase import Client


@dataclass
class Totals:
    gold: float
    income: float
    expenses: float
    net: float


def get_current_week(sb: Client) -> int:
    row = sb.table("app_state").select("current_week").eq("id", 1).execute().data[0]
    return int(row["current_week"])


def set_current_week(sb: Client, week: int) -> None:
    sb.table("app_state").update({"current_week": week}).eq("id", 1).execute()


def get_ledger_totals(sb: Client, week: Optional[int] = None) -> Totals:
    """Compute gold and (optionally) this-week income/expense from ledger."""
    if week is None:
        week = get_current_week(sb)

    # Current gold: sum all ins - outs (all weeks)
    rows = sb.table("ledger_entries").select("direction,amount").execute().data
    gold = 0.0
    for r in rows:
        amt = float(r["amount"])
        if r["direction"] == "in":
            gold += amt
        else:
            gold -= amt

    # This week breakdown
    wk_rows = sb.table("ledger_entries").select("direction,amount").eq("week", week).execute().data
    income = sum(float(r["amount"]) for r in wk_rows if r["direction"] == "in")
    expenses = sum(float(r["amount"]) for r in wk_rows if r["direction"] == "out")
    net = income - expenses
    return Totals(gold=gold, income=income, expenses=expenses, net=net)


def add_ledger_entry(
    sb: Client,
    *,
    week: int,
    direction: str,
    amount: float,
    category: str,
    note: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Insert a ledger entry in a schema-tolerant way.

    Some deployments have legacy column `meta` only, others have `metadata` only,
    and some have both. We try the safest payload first, then fall back.
    """
    md: Dict[str, Any] = metadata or {}

    payload_both = {
        "week": week,
        "direction": direction,
        "amount": amount,
        "category": category,
        "note": note,
        "metadata": md,
        "meta": md,
    }
    try:
        sb.table("ledger_entries").insert(payload_both).execute()
        return
    except Exception:
        pass

    payload_metadata = {
        "week": week,
        "direction": direction,
        "amount": amount,
        "category": category,
        "note": note,
        "metadata": md,
    }
    try:
        sb.table("ledger_entries").insert(payload_metadata).execute()
        return
    except Exception:
        pass

    payload_meta = {
        "week": week,
        "direction": direction,
        "amount": amount,
        "category": category,
        "note": note,
        "meta": md,
    }
    sb.table("ledger_entries").insert(payload_meta).execute()


# Backwards-friendly alias
compute_totals = get_ledger_totals
