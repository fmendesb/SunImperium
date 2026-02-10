import streamlit as st

from utils.nav import page_config, sidebar
from utils.supabase_client import get_supabase
from utils.state import ensure_bootstrap
from utils.ledger import get_current_week
from utils.dm import dm_gate
from utils.undo import log_action
from utils.war import Force, simulate_battle


def rows_to_force(rows: list[dict]) -> Force:
    """Convert squad_members rows into a Force.

    We normalize unit_type strings so older/looser data doesn't break the sim.
    """
    buckets = {"guardian": 0, "archer": 0, "mage": 0, "cleric": 0, "others": 0}
    for r in rows or []:
        t = (r.get("unit_type") or "").strip().lower()
        q = int(r.get("quantity") or 0)
        if q <= 0:
            continue
        if t.startswith("guard"):
            buckets["guardian"] += q
        elif t.startswith("arch"):
            buckets["archer"] += q
        elif t.startswith("mage"):
            buckets["mage"] += q
        elif t.startswith("cler"):
            buckets["cleric"] += q
        else:
            buckets["others"] += q
    return Force(
        guardians=buckets["guardian"],
        archers=buckets["archer"],
        mages=buckets["mage"],
        clerics=buckets["cleric"],
        others=buckets["others"],
    )

UNDO_CATEGORY = "war"

page_config("War Simulator", "🩸")
sidebar("🩸 War Simulator")

sb = get_supabase()
ensure_bootstrap(sb)
week = get_current_week(sb)

# Cache unit catalog so we can infer unit_type when squad_members only stores unit_id
try:
    _units = sb.table("moonblade_units").select("id,unit_type").execute().data or []
except Exception:
    _units = []
UNIT_TYPE_BY_ID = {u.get("id"): (u.get("unit_type") or "Other") for u in _units}


def fetch_squad_member_rows(squad_id) -> list[dict]:
    """Fetch squad member rows.

    We prefer unit_id-based membership (players recruit specific units). Some schemas also store unit_type.
    We normalize the returned rows to always include: id, unit_id, unit_type, quantity.
    """
    # Try the richest select first.
    # NOTE: PostgREST raises hard errors if a selected column doesn't exist.
    # We progressively fall back across known schema variants.
    rows: list[dict] = []
    try:
        rows = (
            sb.table("squad_members")
            .select("id,unit_id,unit_type,quantity")
            .eq("squad_id", squad_id)
            .execute()
            .data
            or []
        )
    except Exception:
        try:
            rows = (
                sb.table("squad_members")
                .select("id,unit_id,quantity")
                .eq("squad_id", squad_id)
                .execute()
                .data
                or []
            )
        except Exception:
            # Oldest fallback: only unit_type stored.
            rows = (
                sb.table("squad_members")
                .select("id,unit_type,quantity")
                .eq("squad_id", squad_id)
                .execute()
                .data
                or []
            )

    for r in rows:
        r["unit_type"] = (r.get("unit_type") or UNIT_TYPE_BY_ID.get(r.get("unit_id"), "Other"))
        r.setdefault("unit_id", None)
    return rows


def rows_agg_for_display(rows: list[dict]) -> list[dict]:
    """Reduce detailed unit rows into unit_type buckets for the sim."""
    out: list[dict] = []
    for r in rows or []:
        out.append({"unit_type": r.get("unit_type"), "quantity": r.get("quantity")})
    return out

st.title("🩸 War Simulator")
st.caption(
    "Pick a friendly squad and (optionally) an enemy squad created by the DM. "
    "Resolve a battle, then apply casualties (DM-only)."
)

# -------------------------
# Load squads
# -------------------------
try:
    squads = (
        sb.table("squads")
        .select("id,name,region,is_enemy")
        .order("is_enemy", desc=False)
        .order("name")
        .execute()
        .data
        or []
    )
except Exception:
    # Backward compatibility: squads table without is_enemy
    squads = sb.table("squads").select("id,name,region").order("name").execute().data or []
    for s in squads:
        s["is_enemy"] = False

friendly_squads = [s for s in squads if not bool(s.get("is_enemy"))]
enemy_squads = [s for s in squads if bool(s.get("is_enemy"))]

if not friendly_squads:
    st.warning("No friendly squads found. Create squads in Moonblade Guild → Military.")
    st.stop()

squad_choice = st.selectbox(
    "Friendly squad",
    options=friendly_squads,
    format_func=lambda r: f"{r.get('name')}" + (f" · {r.get('region')}" if r.get("region") else ""),
)

ally_rows = fetch_squad_member_rows(squad_choice["id"])
ally = rows_to_force(rows_agg_for_display(ally_rows))

st.subheader("Friendly force")
colA, colB, colC, colD, colE = st.columns(5)
colA.metric("Guardians", ally.guardians)
colB.metric("Archers", ally.archers)
colC.metric("Mages", ally.mages)
colD.metric("Clerics", ally.clerics)
colE.metric("Others", ally.others)

st.divider()
st.subheader("Enemy force")

use_enemy_squad = st.toggle(
    "Use a DM enemy squad",
    value=bool(enemy_squads),
    help="If you have enemy squads created in DM Console, you can pick one here.",
)

enemy_squad_choice = None
if use_enemy_squad and enemy_squads:
    enemy_squad_choice = st.selectbox(
        "Enemy squad",
        options=enemy_squads,
        format_func=lambda r: f"{r.get('name')}" + (f" · {r.get('region')}" if r.get("region") else ""),
    )
    enemy_rows = fetch_squad_member_rows(enemy_squad_choice["id"])
    enemy = rows_to_force(rows_agg_for_display(enemy_rows))

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Guardians", enemy.guardians)
    c2.metric("Archers", enemy.archers)
    c3.metric("Mages", enemy.mages)
    c4.metric("Clerics", enemy.clerics)
    c5.metric("Others", enemy.others)
else:
    st.caption("Manual input")
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

if st.button("Resolve battle", type="primary"):
    st.session_state["war_result"] = simulate_battle(ally, enemy)

result = st.session_state.get("war_result")
if not result:
    st.stop()

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
    "No side is ever wiped to zero survivors (sim clamps at least 1 remaining)."
)

# -------------------------
# Apply results
# -------------------------
st.divider()
st.subheader("Apply casualties (DM)")

if not dm_gate("Apply battle results", key="war_apply"):
    st.warning("Locked. Use DM password to apply changes.")
    st.stop()

apply_enemy = bool(enemy_squad_choice)

st.caption("Applies remaining counts to squad(s). If an enemy squad is selected, it will be updated too.")

if st.button("Apply to squads", type="secondary"):
    def apply_remaining_to_rows(squad_id, rows: list[dict], remaining_by_type: dict):
        """Apply remaining counts to detailed (unit_id-based) squad rows.

        We reduce each unit_type bucket proportionally across the underlying unit rows.
        This avoids requiring a unit_type-only schema and keeps recruitment-by-unit intact.
        """
        # Group current rows by unit_type
        by_type: dict[str, list[dict]] = {}
        for r in rows:
            t = (r.get("unit_type") or "Other")
            by_type.setdefault(t, []).append(r)

        for t, rlist in by_type.items():
            cur_total = sum(int(x.get("quantity") or 0) for x in rlist)
            target = int(remaining_by_type.get(t, 0))
            if cur_total <= 0:
                continue
            if target < 0:
                target = 0

            # Scale quantities
            ratio = target / cur_total
            new_q = []
            for x in rlist:
                q = int(x.get("quantity") or 0)
                nq = int(q * ratio)
                new_q.append(nq)

            # Distribute leftover to reach exact target (deterministic order)
            leftover = target - sum(new_q)
            if leftover > 0:
                # Give +1 to the first N rows
                for i in range(min(leftover, len(new_q))):
                    new_q[i] += 1
            elif leftover < 0:
                # Remove 1 from rows that still have >0
                to_remove = -leftover
                for i in range(len(new_q)):
                    if to_remove <= 0:
                        break
                    if new_q[i] > 0:
                        new_q[i] -= 1
                        to_remove -= 1

            # Persist
            for x, nq in zip(rlist, new_q):
                sb.table("squad_members").update({"quantity": int(nq)}).eq("id", x["id"]).execute()

    # Friendly squad update
    remaining_ally = result.ally_remaining.as_dict()
    apply_remaining_to_rows(squad_choice["id"], ally_rows, remaining_ally)

    # Enemy squad update (if used)
    if apply_enemy and enemy_squad_choice is not None:
        remaining_enemy = result.enemy_remaining.as_dict()
        apply_remaining_to_rows(enemy_squad_choice["id"], enemy_rows, remaining_enemy)

    # War log (best-effort across schema variants)
    war_row = {
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
            "enemy_squad_id": enemy_squad_choice["id"] if enemy_squad_choice else None,
        },
    }
    try:
        sb.table("wars").insert(war_row).execute()
    except Exception:
        # older schema used enemy_force
        try:
            war_row2 = dict(war_row)
            war_row2["enemy_force"] = war_row2.pop("enemy")
            sb.table("wars").insert(war_row2).execute()
        except Exception:
            pass

    log_action(
        sb,
        category=UNDO_CATEGORY,
        action="apply_war",
        payload={
            "week": week,
            "friendly_squad_id": squad_choice["id"],
            "enemy_squad_id": enemy_squad_choice["id"] if enemy_squad_choice else None,
            "before_friendly": ally.as_dict(),
            "after_friendly": remaining_ally,
        },
    )

    st.success("Applied.")
    st.rerun()
