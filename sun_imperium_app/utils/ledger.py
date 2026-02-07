from __future__ import annotations

from dataclasses import dataclass
from supabase import Client


def _try_insert(sb: Client, payload: dict) -> None:
    """Insert into ledger_entries with schema drift tolerance.

    PostgREST rejects unknown columns, and older DBs may have only `meta`
    while newer ones may have `metadata` (or both). We attempt a best-first
    insert and retry with reduced payloads based on the error.
    """

    try:
        sb.table("ledger_entries").insert(payload).execute()
        return
    except Exception as e:  # postgrest.exceptions.APIError or httpx errors
        msg = str(e).lower()

    # Retry without `metadata`
    if "metadata" in payload and ("column" in msg and "metadata" in msg):
        p2 = dict(payload)
        p2.pop("metadata", None)
        sb.table("ledger_entries").insert(p2).execute()
        return

    # Retry without `meta`
    if "meta" in payload and ("column" in msg and "meta" in msg):
        p2 = dict(payload)
        p2.pop("meta", None)
        sb.table("ledger_entries").insert(p2).execute()
        return

    # Last resort: try with only common fields
    p3 = {k: payload[k] for k in ["week", "direction", "amount", "category", "note"] if k in payload}
    sb.table("ledger_entries").insert(p3).execute()


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


def get_ledger_totals(sb: Client, week: int | None = None) -> Totals:
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
    metadata: dict | None = None,
) -> None:
    payload = {
        "week": week,
        "direction": direction,
        "amount": amount,
        "category": category,
        "note": note,
        "metadata": metadata or {},
        "meta": metadata or {},  # backward compat with early schema
    }
    _try_insert(sb, payload)


# Backwards-friendly alias
compute_totals = get_ledger_totals
