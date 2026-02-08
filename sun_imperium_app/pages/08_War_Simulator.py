import streamlit as st

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils.dm import dm_gate
from utils.undo import log_action
from utils.war import Force, simulate_battle

UNDO_CATEGORY = "war"

page_config("War Simulator", "🩸")
sidebar("🩸 War Simulator")

sb = get_supabase()
ensure_bootstrap(sb)
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

members = sb.table("squad_members").select("unit_type,quantity").eq("squad_id", squad_choice["id"]).execute().data
ally = Force.from_rows(members)

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
    result = simulate_battle(ally, enemy)
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
                sb.table("squad_members").upsert(
                    {"squad_id": squad_choice["id"], "unit_type": unit_type, "quantity": int(qty)}
                ).execute()

            # Record war log
            sb.table("wars").insert(
                {
                    "week": week,
                    "squad_id": squad_choice["id"],
                    "enemy_force": enemy.as_dict(),
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
