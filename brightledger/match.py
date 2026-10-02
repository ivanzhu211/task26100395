"""Employer match settlement for a single employee and a single year."""

from __future__ import annotations

from .plan import (
    BPS_DENOMINATOR,
    MAX_SALARY_CENTS,
    MIN_SALARY_CENTS,
    Plan,
)

_HALF_BPS = BPS_DENOMINATOR // 2


def _check_domain(salary: int, deferral: int) -> None:
    if not (MIN_SALARY_CENTS <= salary <= MAX_SALARY_CENTS):
        raise ValueError("salary out of legal range")
    if not (0 <= deferral <= salary // 10):
        raise ValueError("deferral out of legal range")


def match(plan: Plan, salary: int, deferral: int) -> int:
    """Return the employer match amount in cents.

    Settlement rules: each tier's salary threshold is floored to cents,
    the deferral fills the tiers in order, each tier's matched amount is
    rounded half-up to cents independently, the tier results are summed,
    and finally the optional annual cap is applied.
    """
    _check_domain(salary, deferral)
    total = 0
    remaining = deferral
    prev_threshold = 0
    for tier in plan.tiers:
        if remaining <= 0:
            break
        threshold = tier.threshold_bps * salary // BPS_DENOMINATOR
        width = threshold - prev_threshold
        amount = remaining if remaining < width else width
        if amount > 0:
            total += (amount * tier.rate_bps + _HALF_BPS) // BPS_DENOMINATOR
            remaining -= amount
        prev_threshold = threshold
    if plan.cap_cents is not None and total > plan.cap_cents:
        total = plan.cap_cents
    return total
