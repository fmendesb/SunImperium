import streamlit as st

from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils.dm import dm_gate
from utils.undo import log_action
from utils.war import Force, simulate_battle
from utils.infrastructure_effects import power_bonus_for_unit_type
from utils.navigation import sidebar_nav

UNDO_CATEGORY = "war"

st.set_page_config(page_title="War Simulator", page_icon="🩸", layout="wide")

sb = get_supabase()
ensure_bootstrap(sb)
sidebar_nav(sb)
week = get_current_week(sb)

st.title("🩸 War Simulator")
st.caption("Select a Moonblade squad, then enter enemy forces. Resolve and (optionally) apply casualties.")

# Load squads
squads = sb.table("squads").select("id,name,region").order("name").execute().data
if not squads:
    st.warning("No squads found. Create squads in the Moonblade Guild page.")
    st.stop()

squad_choice = st.selectbox(
    "Friendly squad",
    options=squads,
    format_func=lambda r: f"{r['name']}",
)

members = (
    sb.table("squad_members")
    .select("unit_type,unit_id,quantity")
    .eq("squad_id", squad_choice["id"])
    .execute()
    .data
)
ally = Force.from_rows(members)

# Compute per-type weights from the squad's actual unit power (moonblade_units.power)
# plus owned infrastructure power boosts (+1/+2/+3 per tier chain).
unit_ids = [m.get("unit_id") for m in (members or []) if m.get("unit_id")]
unit_powers = {}
if unit_ids:
    # fetch in chunks (supabase 'in' can be finicky on long lists)
    rows = sb.table("moonblade_units").select("id,unit_type,power").in_("id", unit_ids).execute().data or []
    unit_powers = {r["id"]: (str(r.get("unit_type") or "others").lower(), float(r.get("power") or 0.0)) for r in rows}

weights: dict[str, float] = {}
totals: dict[str, float] = {"guardian": 0.0, "archer": 0.0, "mage": 0.0, "cleric": 0.0, "others": 0.0}
counts: dict[str, int] = {k: 0 for k in totals}
for m in (members or []):
    t = str(m.get("unit_type") or "others").lower()
    q = int(m.get("quantity") or 0)
    if t not in totals:
        t = "others"
    # Prefer explicit unit power when unit_id is present
    power = 0.0
    uid = m.get("unit_id")
    if uid and uid in unit_powers:
        t_from_id, p = unit_powers[uid]
        t = t_from_id or t
        power = p
    if power <= 0:
        power = 1.0
    # Apply infrastructure power bonus per unit type
    power += float(power_bonus_for_unit_type(sb, t))
    totals[t] += power * max(0, q)
    counts[t] += max(0, q)

for t, total_power in totals.items():
    if counts[t] > 0:
        weights[t] = total_power / float(counts[t])

st.subheader("Friendly force")
colA, colB, colC, colD, colE = st.columns(5)
colA.metric("Guardians", ally.guardians)
colB.metric("Archers", ally.archers)
colC.metric("Mages", ally.mages)
colD.metric("Clerics", ally.clerics)
colE.metric("Others", ally.others)

st.divider()
st.subheader("Enemy force (DM input)")

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    e_guardians = st.number_input("Enemy Guardians", min_value=0, value=0, step=1)
with c2:
    e_archers = st.number_input("Enemy Archers", min_value=0, value=0, step=1)
with c3:
    e_mages = st.number_input("Enemy Mages", min_value=0, value=0, step=1)
with c4:
    e_clerics = st.number_input("Enemy Clerics", min_value=0, value=0, step=1)
with c5:
    e_others = st.number_input("Enemy Others", min_value=0, value=0, step=1)

enemy = Force(
    guardians=int(e_guardians),
    archers=int(e_archers),
    mages=int(e_mages),
    clerics=int(e_clerics),
    others=int(e_others),
)

if st.button("Resolve battle"):
    result = simulate_battle(ally, enemy, ally_weights=weights)
    st.session_state["war_result"] = result

result = st.session_state.get("war_result")
if result:
    st.divider()
    st.subheader("Outcome")
    st.write(f"**Winner:** {result.winner.upper()}")
    st.caption(f"Power: Ally {result.ally_power:,.1f} · Enemy {result.enemy_power:,.1f}")

    r1, r2 = st.columns(2)
    with r1:
        st.markdown("### Ally")
        st.write("Casualties:")
        st.json(result.ally_casualties.as_dict())
        st.write("Remaining:")
        st.json(result.ally_remaining.as_dict())
    with r2:
        st.markdown("### Enemy")
        st.write("Casualties:")
        st.json(result.enemy_casualties.as_dict())
        st.write("Remaining:")
        st.json(result.enemy_remaining.as_dict())

    st.info(
        "Rules: guardians > archers > mages > guardians. Clerics buff allies. "
        "No side is ever wiped to zero survivors (the sim clamps at least 1 remaining)."
    )

    st.divider()
    st.subheader("Apply casualties (DM)")
    if dm_gate("Apply battle results", key="war_apply"):
        if st.button("Apply to friendly squad roster"):
            # Update squad members to remaining
            remaining = result.ally_remaining.as_dict()
            for unit_type, qty in remaining.items():
                existing = (
                    sb.table("squad_members")
                    .select("id")
                    .eq("squad_id", squad_choice["id"])
                    .eq("unit_type", unit_type)
                    .limit(1)
                    .execute()
                    .data
                )
                if existing:
                    sb.table("squad_members").update({"quantity": int(qty)}).eq("id", existing[0]["id"]).execute()
                else:
                    sb.table("squad_members").insert(
                        {"squad_id": squad_choice["id"], "unit_type": unit_type, "quantity": int(qty)}
                    ).execute()

            # Record war log
            sb.table("wars").insert(
                {
                    "week": week,
                    "squad_id": squad_choice["id"],
                    "enemy": enemy.as_dict(),
                    "result": {
                        "winner": result.winner,
                        "ally_power": result.ally_power,
                        "enemy_power": result.enemy_power,
                        "ally_casualties": result.ally_casualties.as_dict(),
                        "enemy_casualties": result.enemy_casualties.as_dict(),
                        "ally_remaining": result.ally_remaining.as_dict(),
                        "enemy_remaining": result.enemy_remaining.as_dict(),
                    },
                }
            ).execute()

            log_action(
                sb,
                category=UNDO_CATEGORY,
                action="apply_war",
                payload={
                    "week": week,
                    "squad_id": squad_choice["id"],
                    "before": ally.as_dict(),
                    "after": remaining,
                },
            )
            st.success("Applied to squad. (Undo for war results can be added next.)")
            st.rerun()
    else:
        st.warning("Locked. Use DM password to apply changes.")
