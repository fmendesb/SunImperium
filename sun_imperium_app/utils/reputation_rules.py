from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RepDerived:
    dc: int
    bonus: int


def derive_dc_bonus(score: int) -> RepDerived:
    """Derive DC and bonus from reputation score.

    Design goal: simple, transparent, and bounded.

    - Every 10 points of reputation shifts the bonus by 1.
    - Bonus is clamped to [-5, +5]
    - Base DC is 15, improved/worsened by the bonus.

    This function is intentionally centralized so the DM can
    tweak the formula in one place later.
    """

    try:
        score_i = int(score)
    except Exception:
        score_i = 0

    bonus = score_i // 10
    if bonus < -5:
        bonus = -5
    if bonus > 5:
        bonus = 5

    dc = 15 - (bonus * 2)
    if dc < 5:
        dc = 5
    if dc > 30:
        dc = 30

    return RepDerived(dc=dc, bonus=bonus)
