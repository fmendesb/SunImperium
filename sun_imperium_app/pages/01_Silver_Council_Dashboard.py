import streamlit as st
import pandas as pd

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week, compute_totals
from utils.infrastructure_effects import production_multiplier, social_points


page_config("Silver Council | Dashboard", "🏛️")
sidebar("🏛 Dashboard")

sb = get_supabase()
ensure_bootstrap(sb)
week = int(get_current_week(sb) or 1)


def _safe_select(table: str, cols_variants: list[str], *, filters: list[tuple[str, str, object]] | None = None, order: str | None = None, desc: bool = False, limit: int | None = None):
    """Best-effort select that tolerates schema drift (missing columns)."""
    filters = filters or []
    last_err = None
    for cols in cols_variants:
        try:
            q = sb.table(table).select(cols)
            for op, key, value in filters:
                if op == "eq":
                    q = q.eq(key, value)
                elif op == "neq":
                    q = q.neq(key, value)
            if order:
                q = q.order(order, desc=desc)
            if limit is not None:
                q = q.limit(limit)
            return q.execute().data or []
        except Exception as e:
            last_err = e
            continue
    return []


tot = compute_totals(sb, week=week)

st.title("🏛️ The Silver Council")
st.caption(f"Overview · Week {week}")

# --- Economy + population snapshot ---
eco_this = _safe_select(
    "economy_week_summary",
    [
        "week,population,survival_ratio,player_payout,tax_income,gross_value,grain_needed,grain_produced,water_needed,water_produced",
        "week,population,survival_ratio,player_payout,tax_income,gross_value",
    ],
    filters=[("eq", "week", week)],
    limit=1,
)

eco_prev = _safe_select(
    "economy_week_summary",
    ["week,population"],
    filters=[("eq", "week", max(1, week - 1))],
    limit=1,
)

settings = _safe_select(
    "economy_settings",
    [
        "id,target_player_payout,war_severity,baseline_price_index",
        "id,target_player_payout,war_severity",
        "id,target_player_payout",
    ],
    filters=[("eq", "id", 1)],
    limit=1,
)

target_payout = float(settings[0].get("target_player_payout") or 75.0) if settings else 75.0
war_sev = float(settings[0].get("war_severity") or 1.0) if settings else 1.0

this_pop = int((eco_this[0].get("population") if eco_this else 0) or 0)
prev_pop = int((eco_prev[0].get("population") if eco_prev else 0) or 0)
pop_delta = (this_pop - prev_pop) if (this_pop and prev_pop) else None

this_payout = float((eco_this[0].get("player_payout") if eco_this else 0) or 0.0)
eco_health = 0.0
if target_payout > 0:
    eco_health = max(0.0, min(999.0, (this_payout / target_payout) * 100.0))

# Gold added this week (player payout entry)
wk_entries = _safe_select(
    "ledger_entries",
    ["week,category,direction,amount,note"],
    filters=[("eq", "week", week)],
)

gold_added = sum(
    float(r.get("amount") or 0)
    for r in wk_entries
    if str(r.get("direction")) == "in" and str(r.get("category")) == "player_payout"
)


top1, top2, top3, top4, top5 = st.columns(5)
with top1:
    st.metric("Moonvault (Gold)", f"{tot.gold:,.0f}")
with top2:
    st.metric("Gold added (this week)", f"{gold_added:,.0f}")
with top3:
    st.metric("Income (this week)", f"{tot.income:,.0f}")
with top4:
    st.metric("Expenses (this week)", f"{tot.expenses:,.0f}")
with top5:
    st.metric("Economy vs baseline", f"{eco_health:,.0f}%")

st.divider()

left, right = st.columns([1.1, 0.9])

with left:
    st.subheader("Population & Survival")

    p1, p2, p3 = st.columns(3)
    with p1:
        st.metric("Population", f"{this_pop:,}" if this_pop else "—", delta=f"{pop_delta:+,}" if pop_delta is not None else None)
    with p2:
        sr = float((eco_this[0].get("survival_ratio") if eco_this else 0) or 0.0)
        st.metric("Survival ratio", f"{sr:.2f}" if eco_this else "—")
    with p3:
        st.metric("War severity", f"{war_sev:.2f}")

    if eco_this and ("grain_needed" in eco_this[0] or "water_needed" in eco_this[0]):
        g = eco_this[0]
        g1, g2 = st.columns(2)
        with g1:
            st.write(
                f"**Grain:** {int(g.get('grain_produced') or 0):,} / {float(g.get('grain_needed') or 0):,.0f} needed"
            )
        with g2:
            st.write(
                f"**Water:** {int(g.get('water_produced') or 0):,} / {float(g.get('water_needed') or 0):,.0f} needed"
            )
    else:
        st.caption("(Food/water details appear after the week’s economy has been computed.)")

    st.subheader("Social & Production")
    try:
        prod_mul = float(production_multiplier(sb) or 1.0)
    except Exception:
        prod_mul = 1.0
    try:
        soc = float(social_points(sb) or 0.0)
    except Exception:
        soc = 0.0

    s1, s2 = st.columns(2)
    with s1:
        st.metric("Production multiplier", f"x{prod_mul:.2f}")
    with s2:
        st.metric("Social points", f"{soc:.0f}")

    st.caption(
        "Social points and production multipliers come from owned infrastructure. "
        "As you stabilize regions and improve reputation, the economy baseline % should rise naturally."
    )

with right:
    st.subheader("Forces & Deployments")

    squads = _safe_select(
        "squads",
        [
            "id,name,region,destination,status,deployed_week,is_enemy",
            "id,name,region,destination,status,deployed_week",
            "id,name,region",
        ],
        order="name",
    )

    # Show only friendly squads here (DM can view enemy squads in DM Console)
    friendly = [s for s in squads if not bool(s.get("is_enemy"))]
    if friendly:
        rows = []
        for s in friendly:
            rows.append(
                {
                    "Squad": s.get("name"),
                    "Region": s.get("region") or "—",
                    "Destination": s.get("destination") or "—",
                    "Status": s.get("status") or "ready",
                    "Deployed": s.get("deployed_week") or "—",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No squads created yet.")

    st.subheader("Active Missions")
    missions_rows: list[dict] = []
    for table, label in [("diplomacy_missions", "Diplomacy"), ("intelligence_missions", "Intelligence")]:
        ms = _safe_select(
            table,
            [
                "id,week,target,objective,status,eta_week,total_success",
                "id,week,target,objective,status,eta_week",
            ],
            filters=[("eq", "status", "active")],
            order="created_at",
            desc=True,
            limit=25,
        )
        for m in ms:
            missions_rows.append(
                {
                    "Type": label,
                    "Target": m.get("target") or "—",
                    "Objective": m.get("objective") or "—",
                    "ETA": m.get("eta_week") or "—",
                    "Week": m.get("week") or "—",
                }
            )
    if missions_rows:
        st.dataframe(pd.DataFrame(missions_rows), use_container_width=True, hide_index=True)
    else:
        st.caption("No active diplomacy/intelligence missions.")


st.divider()

# Upkeep breakdown chips for this week
def _sum_out(prefix: str) -> float:
    return sum(
        float(r.get("amount") or 0)
        for r in wk_entries
        if str(r.get("direction")) == "out" and str(r.get("category") or "").startswith(prefix)
    )


u1, u2, u3, u4 = st.columns(4)
with u1:
    st.metric("Moonblade upkeep", f"{_sum_out('moonblade_'):,.0f}")
with u2:
    st.metric("Dawnbreakers upkeep", f"{_sum_out('dawnbreakers_'):,.0f}")
with u3:
    st.metric("Diplomacy upkeep", f"{_sum_out('diplomacy_'):,.0f}")
with u4:
    st.metric("Infrastructure upkeep", f"{_sum_out('infrastructure_'):,.0f}")

st.info(
    "Tip: recruiting units and buying infrastructure immediately reduces the Moonvault. "
    "Weekly income/upkeep is applied when the DM advances the week."
)
