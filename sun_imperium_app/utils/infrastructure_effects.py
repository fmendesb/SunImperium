from __future__ import annotations

from dataclasses import dataclass
from supabase import Client


@dataclass(frozen=True)
class InfraEffect:
    """A lightweight, human-facing effect descriptor.

    These values are grounded in the tables described in the Sun Imperium APP
    document (Infrastructure section).
    """

    kind: str  # e.g. 'power_bonus', 'success_bonus_pct', 'multiplier', 'social_bonus'
    target: str  # e.g. 'archer', 'diplomacy', 'economy', 'social'
    value: float
    unit: str  # '', '%', 'x'


# Canon infrastructure effects (name -> effect)
# Source: Sun Imperium APP.docx infrastructure table and notes.
_EFFECTS: dict[str, InfraEffect] = {
    # Military power bonuses
    "Barracks": InfraEffect("power_bonus", "guardian", 1, ""),
    "Enchanted Weaponry": InfraEffect("power_bonus", "guardian", 2, ""),
    "Celestial Citadel": InfraEffect("power_bonus", "guardian", 3, ""),
    "Archery Range": InfraEffect("power_bonus", "archer", 1, ""),
    "Enchanted Artillery": InfraEffect("power_bonus", "archer", 2, ""),
    "Moonlit Eyrie": InfraEffect("power_bonus", "archer", 3, ""),
    "Mage Tower": InfraEffect("power_bonus", "mage", 1, ""),
    "Enchanted Catalysts": InfraEffect("power_bonus", "mage", 2, ""),
    "Arcana Nexus": InfraEffect("power_bonus", "mage", 3, ""),
    "Temple": InfraEffect("power_bonus", "cleric", 1, ""),
    "Enchanted Idols": InfraEffect("power_bonus", "cleric", 2, ""),
    "Ethereal Sanctuary": InfraEffect("power_bonus", "cleric", 3, ""),

    # Intelligence success bonuses
    "Safe Houses": InfraEffect("success_bonus_pct", "intelligence", 10, "%"),
    "Shadow Network": InfraEffect("success_bonus_pct", "intelligence", 20, "%"),
    "Phantom Academy": InfraEffect("success_bonus_pct", "intelligence", 35, "%"),

    # Diplomacy success bonuses
    "Diplomatic Academy": InfraEffect("success_bonus_pct", "diplomacy", 10, "%"),
    "Treaty Archives": InfraEffect("success_bonus_pct", "diplomacy", 20, "%"),
    "Embassy": InfraEffect("success_bonus_pct", "diplomacy", 35, "%"),

    # Resources multipliers
    "Celestial Greenhouse": InfraEffect("multiplier", "production", 1.5, "x"),
    "Moonlit Irrigation System": InfraEffect("multiplier", "production", 1.5, "x"),
    "Lunar Energy Reactor": InfraEffect("multiplier", "production", 3.0, "x"),

    # Social status bonuses (influences economic production)
    "Primary Education Hub": InfraEffect("social_bonus", "social", 1, ""),
    "Healing Sanctums": InfraEffect("social_bonus", "social", 1, ""),
    "Leisure Facilities": InfraEffect("social_bonus", "social", 2, ""),
}


# Explicit prerequisite chains (name -> prerequisite name)
_PREREQS: dict[str, str] = {
    # Military
    "Enchanted Weaponry": "Barracks",
    "Celestial Citadel": "Enchanted Weaponry",
    "Enchanted Artillery": "Archery Range",
    "Moonlit Eyrie": "Enchanted Artillery",
    "Enchanted Catalysts": "Mage Tower",
    "Arcana Nexus": "Enchanted Catalysts",
    "Enchanted Idols": "Temple",
    "Ethereal Sanctuary": "Enchanted Idols",

    # Intelligence
    "Shadow Network": "Safe Houses",
    "Phantom Academy": "Shadow Network",

    # Diplomacy
    "Treaty Archives": "Diplomatic Academy",
    "Embassy": "Treaty Archives",

    # Communication
    "Astral Communication Zone": "Astral Communication Stones",
    "Astral Communication Network": "Astral Communication Zone",

    # Logistics
    "Mooncharged Airships": "Lunar Gliders",
    "Mystical Transportation Hub": "Mooncharged Airships",

    # Resources
    "Moonlit Irrigation System": "Celestial Greenhouse",
    "Lunar Energy Reactor": "Moonlit Irrigation System",
}


def effect_for_infrastructure(name: str) -> InfraEffect | None:
    return _EFFECTS.get((name or "").strip())


def prereq_name_for_infrastructure(name: str) -> str | None:
    return _PREREQS.get((name or "").strip())


def get_owned_infrastructure_names(sb: Client) -> set[str]:
    infra = sb.table("infrastructure").select("id,name").execute().data
    owned = sb.table("infrastructure_owned").select("infrastructure_id,owned").execute().data
    owned_ids = {r["infrastructure_id"] for r in owned if bool(r.get("owned"))}
    return {r["name"] for r in infra if r["id"] in owned_ids}


def power_bonus_for_unit_type(sb: Client, unit_type: str) -> float:
    """Total power bonus from owned infrastructure for a unit_type."""
    unit_type = (unit_type or "").strip().lower()
    owned_names = get_owned_infrastructure_names(sb)
    bonus = 0.0
    for name in owned_names:
        eff = effect_for_infrastructure(name)
        if eff and eff.kind == "power_bonus" and eff.target == unit_type:
            bonus += float(eff.value)
    return bonus


def success_bonus_pct_for_category(sb: Client, category: str) -> float:
    """Total success bonus % from owned infrastructure (diplomacy/intelligence)."""
    category = (category or "").strip().lower()
    owned_names = get_owned_infrastructure_names(sb)
    bonus = 0.0
    for name in owned_names:
        eff = effect_for_infrastructure(name)
        if eff and eff.kind == "success_bonus_pct" and eff.target == category:
            bonus += float(eff.value)
    return bonus


def describe_infrastructure_effect(name: str) -> str:
    """Human-friendly effect string for UI."""
    effs = EFFECTS.get((name or "").strip())
    if not effs:
        return ""
    parts: list[str] = []
    for e in effs:
        kind = e.get("kind")
        target = (e.get("target") or "").replace("_", " ")
        value = e.get("value")
        if kind == "power_bonus":
            parts.append(f"+{value} {target} power")
        elif kind == "success_bonus":
            parts.append(f"+{value}% {target} success")
        elif kind == "production_bonus":
            parts.append(f"+{value}% economy output")
        elif kind == "social_bonus":
            parts.append(f"+{value} social points")
        elif kind == "multiplier":
            # e.g., x1.05
            try:
                parts.append(f"x{float(value):.2f} {target}")
            except Exception:
                parts.append(f"x{value} {target}")
        else:
            parts.append(f"{kind}: {value} {target}".strip())
    return " · ".join(parts)


def _owned_names(sb) -> list[str]:
    try:
        rows = sb.table("infrastructure_owned").select("name").execute().data or []
        return [str(r.get("name") or "").strip() for r in rows if r.get("name")]
    except Exception:
        return []


def production_multiplier_owned(sb) -> float:
    mult = 1.0
    for name in _owned_names(sb):
        for e in EFFECTS.get(name, []):
            if e.get("kind") == "multiplier" and e.get("target") in {"production", "economy"}:
                try:
                    mult *= float(e.get("value") or 1.0)
                except Exception:
                    pass
            if e.get("kind") == "production_bonus":
                try:
                    mult *= 1.0 + (float(e.get("value") or 0.0) / 100.0)
                except Exception:
                    pass
    return float(mult)


def social_points_owned(sb) -> int:
    pts = 0
    for name in _owned_names(sb):
        for e in EFFECTS.get(name, []):
            if e.get("kind") == "social_bonus":
                try:
                    pts += int(e.get("value") or 0)
                except Exception:
                    pass
    return int(pts)


def production_multiplier_all(sb=None) -> float:
    """Baseline assumes all infrastructure is owned (optimistic baseline)."""
    mult = 1.0
    for name, effs in EFFECTS.items():
        for e in effs:
            if e.get("kind") == "multiplier" and e.get("target") in {"production", "economy"}:
                try:
                    mult *= float(e.get("value") or 1.0)
                except Exception:
                    pass
            if e.get("kind") == "production_bonus":
                try:
                    mult *= 1.0 + (float(e.get("value") or 0.0) / 100.0)
                except Exception:
                    pass
    return float(mult)


def social_points_all(sb=None) -> int:
    pts = 0
    for name, effs in EFFECTS.items():
        for e in effs:
            if e.get("kind") == "social_bonus":
                try:
                    pts += int(e.get("value") or 0)
                except Exception:
                    pass
    return int(pts)
