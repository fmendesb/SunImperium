from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepDerived:
    dc: int
    bonus: int


def derive_dc_bonus(score: int) -> RepDerived:
    """Derive DC and bonus from reputation score.

    Canon score range: -2 .. 12 (per Sun Imperium APP doc).

    The doc describes a *required roll* model for influence:
    - reputation 12 requires a roll of 0 (auto success)
    - reputation -2 requires at least 23

    We implement a simple, transparent approximation that satisfies those
    anchor points and produces distinct values across the range:
    
    required_roll = max(0, 23 - 2 * (score + 2))

    We also expose a small bonus number (for UI / helper math) derived from
    reputation, centered around score 5.
    """

    try:
        score_i = int(score)
    except Exception:
        score_i = 0

    # Clamp to expected range
    if score_i < -2:
        score_i = -2
    if score_i > 12:
        score_i = 12

    dc = 23 - 2 * (score_i + 2)
    if dc < 0:
        dc = 0

    bonus = score_i - 5
    if bonus < -5:
        bonus = -5
    if bonus > 5:
        bonus = 5

    return RepDerived(dc=dc, bonus=bonus)
