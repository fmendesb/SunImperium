import streamlit as st

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals
from utils.infrastructure_effects import production_multiplier, social_points


page_config("Silver Council | Dashboard", "🏛️")
sidebar("🏛 Dashboard")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

# The week shown on most summaries is the *last computed* week.
# DM Console computes economy + posts income for the week being closed, then increments current_week.
summary_week = max(1, week - 1)

tot_current = compute_totals(sb, week=week)
tot_summary = compute_totals(sb, week=summary_week)

# Gold added is specifically the player payout (not other refunds/undos)
try:
    pay_rows = (
        sb.table("ledger_entries")
        .select("direction,amount,category")
        .eq("week", summary_week)
        .execute()
        .data
        or []
    )
    gold_added = sum(
        float(r.get("amount") or 0)
        for r in pay_rows
        if r.get("direction") == "in" and str(r.get("category") or "") == "player_payout"
    )
except Exception:
    gold_added = float(tot_summary.income)

st.title("🏛️ The Silver Council")
st.caption(f"Dashboard · Current week {week} · Last computed week {summary_week}")

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Moonvault (Gold)", f"{tot_current.gold:,.0f}")
with c2:
    st.metric("Gold added (last week)", f"{gold_added:,.0f}")
with c3:
    st.metric("Income (last week)", f"{tot_summary.income:,.0f}")
with c4:
    st.metric("Expenses (last week)", f"{tot_summary.expenses:,.0f}")

st.divider()

# Economy snapshot (from last computed week)
eco = sb.table("economy_week_summary").select(
    "population,survival_ratio,player_payout,tax_income,gross_value,grain_needed,grain_produced,water_needed,water_produced"
).eq("week", summary_week).limit(1).execute().data

# Baseline economy week (used for % display)
baseline = sb.table("economy_week_summary").select("gross_value").eq("week", 1).limit(1).execute().data
baseline_gross = float((baseline[0].get("gross_value") if baseline else 0) or 0)

if eco:
    row = eco[0]
    gross = float(row.get("gross_value") or 0)
    # If baseline hasn't been computed yet, treat the first available week as 100%
    baseline_pct = 100.0
    if baseline_gross > 0:
        baseline_pct = (gross / baseline_gross) * 100.0

    # Population (current vs last)
    pop_now_rows = sb.table("population_state").select("population").eq("week", week).limit(1).execute().data
    pop_prev_rows = sb.table("population_state").select("population").eq("week", summary_week).limit(1).execute().data
    pop_now = int((pop_now_rows[0].get("population") if pop_now_rows else 450_000) or 450_000)
    pop_prev = int((pop_prev_rows[0].get("population") if pop_prev_rows else int(row.get("population") or 450_000)) or 450_000)

    war_rows = sb.table("economy_settings").select("war_severity").eq("id", 1).limit(1).execute().data
    war_sev = float((war_rows[0].get("war_severity") if war_rows else 1.0) or 1.0)
    war_on = "Yes" if war_sev >= 0.5 else "No"

    e1, e2, e3, e4 = st.columns(4)
    with e1:
        st.metric("Population", f"{pop_now:,}", delta=f"{pop_now - pop_prev:+,}")
    with e2:
        st.metric("Survival ratio (last week)", f"{float(row.get('survival_ratio') or 0):.2f}")
    with e3:
        st.metric("Economy vs baseline", f"{baseline_pct:.0f}%")
    with e4:
        st.metric("War ongoing", war_on)

    g1, g2 = st.columns(2)
    with g1:
        st.write(
            f"**Grain:** {int(row.get('grain_produced') or 0):,} / {float(row.get('grain_needed') or 0):,.0f} needed"
        )
    with g2:
        st.write(
            f"**Water:** {int(row.get('water_produced') or 0):,} / {float(row.get('water_needed') or 0):,.0f} needed"
        )
else:
    st.warning(
        "Economy not computed yet for the last week. Use DM Console → Advance Week. "
        "(After advancing, the dashboard shows the previous week’s results.)"
    )

# Upkeep breakdown chips for this week
wk_rows = sb.table("ledger_entries").select("category,direction,amount").eq("week", summary_week).execute().data

def sum_cat(prefix: str) -> float:
    return sum(float(r["amount"]) for r in wk_rows if r["direction"] == "out" and r["category"].startswith(prefix))

u1, u2, u3, u4 = st.columns(4)
with u1:
    st.metric("Moonblade Guild upkeep", f"{sum_cat('moonblade_'):,.0f}")
with u2:
    st.metric("Dawnbreakers upkeep", f"{sum_cat('dawnbreakers_'):,.0f}")
with u3:
    st.metric("Diplomacy upkeep", f"{sum_cat('diplomacy_'):,.0f}")
with u4:
    st.metric("Infrastructure upkeep", f"{sum_cat('infrastructure_'):,.0f}")

st.info("Tip: Infrastructure purchases and recruiting units immediately reduce the Moonvault. Weekly income/upkeep is applied when the week advances.")

st.divider()

# Quick infra snapshot (helps players see progress)
try:
    pm = float(production_multiplier(sb) or 1.0)
    sp = int(social_points(sb) or 0)
    i1, i2 = st.columns(2)
    with i1:
        st.metric("Production multiplier (infra)", f"x{pm:.2f}")
    with i2:
        st.metric("Social points (infra)", f"{sp}")
except Exception:
    pass
