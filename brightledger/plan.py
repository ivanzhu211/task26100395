"""Plan definitions for the BrightLedger 401(k) safe-harbor match library.

All money amounts are integer cents.  All percentages are integer basis
points (10000 bps == 100%).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

BPS_DENOMINATOR = 10000
MAX_THRESHOLD_BPS = 1000
MAX_RATE_BPS = 10000
MIN_SALARY_CENTS = 2_500_000
MAX_SALARY_CENTS = 50_000_000


@dataclass(frozen=True)
class Tier:
    """One match tier.

    threshold_bps: cumulative deferral threshold as basis points of salary.
    rate_bps: match rate applied to deferrals falling in this tier.
    """

    threshold_bps: int
    rate_bps: int


@dataclass(frozen=True)
class Plan:
    """An employer match formula: tiers plus an optional annual cap (cents)."""

    tiers: Tuple[Tier, ...]
    cap_cents: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tiers", tuple(self.tiers))
        prev = -1
        for tier in self.tiers:
            if not (0 <= tier.threshold_bps <= MAX_THRESHOLD_BPS):
                raise ValueError("tier threshold out of range")
            if tier.threshold_bps <= prev:
                raise ValueError("tier thresholds must be strictly increasing")
            if not (0 <= tier.rate_bps <= MAX_RATE_BPS):
                raise ValueError("tier rate out of range")
            prev = tier.threshold_bps
        if self.cap_cents is not None and self.cap_cents < 0:
            raise ValueError("cap must be non-negative")


def basic_plan() -> Plan:
    """The statutory basic safe-harbor formula (no annual cap)."""
    return Plan(
        tiers=(
            Tier(threshold_bps=300, rate_bps=10000),
            Tier(threshold_bps=500, rate_bps=5000),
        ),
        cap_cents=None,
    )
