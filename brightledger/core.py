"""BrightLedger 401(k) 安全港配比：核心类型与逐档结算。

约定：
- 金额一律为整数分。
- 比例一律为整数基点，10_000 基点 = 100%。
- 每档金额乘匹配率后单独四舍五入到分，恰好半分向上。
"""
from __future__ import annotations

from dataclasses import dataclass

BASIS_POINTS = 10_000
MIN_SALARY_CENTS = 2_500_000
MAX_SALARY_CENTS = 50_000_000
MAX_DEFERRAL_BP = 1_000
HALF_BASIS_POINTS = BASIS_POINTS // 2


@dataclass(frozen=True)
class Tier:
    """单档：累计缴费阈值（工资的基点比例）与该档匹配率（基点）。"""

    threshold_bp: int
    rate_bp: int


@dataclass(frozen=True)
class Plan:
    """配比公式：若干档 + 可选年度雇主金额上限（分）。"""

    tiers: tuple[Tier, ...]
    cap_cents: int | None = None

    def __post_init__(self) -> None:
        prev = -1
        for tier in self.tiers:
            if not 0 <= tier.threshold_bp <= MAX_DEFERRAL_BP:
                raise ValueError(f"阈值越界: {tier.threshold_bp}")
            if tier.threshold_bp <= prev:
                raise ValueError("阈值必须严格递增")
            if not 0 <= tier.rate_bp <= BASIS_POINTS:
                raise ValueError(f"匹配率越界: {tier.rate_bp}")
            prev = tier.threshold_bp
        if self.cap_cents is not None and self.cap_cents < 0:
            raise ValueError("上限不能为负")


BASIC_PLAN = Plan(tiers=(Tier(300, 10_000), Tier(500, 5_000)))


def round_half_up_cents(amount_cents: int, rate_bp: int) -> int:
    """amount_cents * rate_bp / 10000 四舍五入到分，半分向上。"""
    return (amount_cents * rate_bp + HALF_BASIS_POINTS) // BASIS_POINTS


def validate_inputs(salary: int, deferral: int) -> None:
    if not MIN_SALARY_CENTS <= salary <= MAX_SALARY_CENTS:
        raise ValueError(f"工资越界: {salary}")
    if not 0 <= deferral <= salary * MAX_DEFERRAL_BP // BASIS_POINTS:
        raise ValueError(f"缴费越界: {deferral}")


def match(plan: Plan, salary: int, deferral: int) -> int:
    """雇主配比金额（分）：逐档填入、逐档取整、求和后应用年度上限。"""
    validate_inputs(salary, deferral)
    total = 0
    prev_threshold = 0
    for tier in plan.tiers:
        threshold = salary * tier.threshold_bp // BASIS_POINTS
        amount = min(max(deferral - prev_threshold, 0), threshold - prev_threshold)
        total += round_half_up_cents(amount, tier.rate_bp)
        prev_threshold = threshold
    if plan.cap_cents is not None:
        total = min(total, plan.cap_cents)
    return total
