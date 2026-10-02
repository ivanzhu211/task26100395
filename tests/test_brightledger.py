"""BrightLedger 401(k) 安全港配比验证库的自动化测试。"""
from __future__ import annotations

import random

import numpy as np
import pytest

from brightledger import BASIC_PLAN, Plan, Tier, certify, match
from brightledger.core import MAX_SALARY_CENTS, MIN_SALARY_CENTS

FULL_RANGE = (MIN_SALARY_CENTS, MAX_SALARY_CENTS)
BP = 10_000


def vec_basic(s: int, d: np.ndarray) -> np.ndarray:
    b1 = s * 300 // BP
    b2 = s * 500 // BP
    a1 = np.minimum(d, b1)
    a2 = np.clip(d - b1, 0, b2 - b1)
    return a1 + (a2 * 5000 + 5000) // BP


def vec_plan(plan: Plan, s: int, d: np.ndarray) -> np.ndarray:
    total = np.zeros_like(d)
    prev = np.zeros_like(d)
    for tier in plan.tiers:
        c = s * tier.threshold_bp // BP
        amount = np.clip(d - prev, 0, c - prev)
        total += (amount * tier.rate_bp + 5000) // BP
        prev = c
    if plan.cap_cents is not None:
        total = np.minimum(total, plan.cap_cents)
    return total


def brute_force_min_counterexample(plan: Plan, s_min: int, s_max: int):
    """对 [s_min, s_max] 逐一工资、逐一缴费穷举，返回最小反例或 None。"""
    for s in range(s_min, s_max + 1):
        d = np.arange(0, s // 10 + 1, dtype=np.int64)
        deficit = vec_basic(s, d) - vec_plan(plan, s, d)
        hits = np.nonzero(deficit >= 1)[0]
        if len(hits):
            return s, int(d[hits[0]])
    return None


# ---------- match 单元测试 ----------


def test_match_basic_formula_example():
    assert match(BASIC_PLAN, 2_500_020, 125_001) == 100_001


def test_match_rounds_half_up_per_tier():
    plan = Plan(tiers=(Tier(1000, 5000),))
    assert match(plan, 2_500_000, 1) == 1  # 0.5 分向上
    assert match(plan, 2_500_000, 3) == 2  # 1.5 分向上
    assert match(plan, 2_500_000, 4) == 2


def test_match_fills_tiers_in_order():
    plan = Plan(tiers=(Tier(100, 10_000), Tier(200, 5000)))
    # 工资 2,500,000：档界 25,000 / 50,000
    assert match(plan, 2_500_000, 30_000) == 25_000 + 2_500


def test_match_beyond_last_tier_unmatched():
    plan = Plan(tiers=(Tier(100, 10_000),))
    assert match(plan, 2_500_000, 250_000) == 25_000


def test_match_cap_applied_after_sum():
    plan = Plan(tiers=(Tier(500, 10_000),), cap_cents=2_000_000)
    assert match(plan, 50_000_000, 2_500_000) == 2_000_000
    assert match(plan, 50_000_000, 5_000_000) == 2_000_000


def test_match_zero_deferral():
    assert match(BASIC_PLAN, 3_000_000, 0) == 0


def test_match_input_validation():
    with pytest.raises(ValueError):
        match(BASIC_PLAN, MIN_SALARY_CENTS - 1, 0)
    with pytest.raises(ValueError):
        match(BASIC_PLAN, 3_000_000, 300_001)
    with pytest.raises(ValueError):
        Plan(tiers=(Tier(500, 10_000), Tier(500, 5000)))
    with pytest.raises(ValueError):
        Plan(tiers=(Tier(1001, 10_000),))


# ---------- 题目规定的两个场景 ----------


def test_four_percent_plan_rejected_with_minimal_counterexample():
    plan = Plan(tiers=(Tier(400, 10_000),))
    result = certify(plan, *FULL_RANGE)
    assert not result.passed
    assert (result.salary, result.deferral) == (2_500_020, 125_001)
    # 反例可由 match 逐分复算
    assert match(BASIC_PLAN, result.salary, result.deferral) == 100_001
    assert match(plan, result.salary, result.deferral) == 100_000


def test_five_percent_plan_with_cap_passes():
    plan = Plan(tiers=(Tier(500, 10_000),), cap_cents=2_000_000)
    assert certify(plan, *FULL_RANGE).passed


def test_five_percent_plan_with_cap_minus_one_rejected():
    plan = Plan(tiers=(Tier(500, 10_000),), cap_cents=1_999_999)
    result = certify(plan, *FULL_RANGE)
    assert not result.passed
    assert (result.salary, result.deferral) == (50_000_000, 2_499_999)
    assert match(BASIC_PLAN, result.salary, result.deferral) == 2_000_000
    assert match(plan, result.salary, result.deferral) == 1_999_999


# ---------- 随机化穷举交叉验证 ----------


def random_plan(rng: random.Random) -> Plan:
    n = rng.randint(1, 4)
    thresholds = sorted(rng.sample(range(0, 1001, 25), n))
    rates = [
        rng.choice([0, 2500, 4999, 5000, 5001, 7500, 9999, 10_000,
                    rng.randint(0, 10_000)])
        for _ in range(n)
    ]
    cap = rng.choice([None, None, rng.randint(0, 2_500_000)])
    return Plan(tiers=tuple(Tier(t, r) for t, r in zip(thresholds, rates)),
                cap_cents=cap)


@pytest.mark.parametrize("seed", range(30))
def test_certify_against_brute_force(seed: int):
    rng = random.Random(seed)
    plan = random_plan(rng)
    s_min = rng.randint(MIN_SALARY_CENTS, MAX_SALARY_CENTS - 40)
    s_max = s_min + rng.randint(5, 40)
    expected = brute_force_min_counterexample(plan, s_min, s_max)
    result = certify(plan, s_min, s_max)
    if expected is None:
        assert result.passed, f"误报反例: {plan} {result}"
    else:
        assert not result.passed
        assert (result.salary, result.deferral) == expected
        # 反例必须能由 match 逐分复算
        assert (match(BASIC_PLAN, result.salary, result.deferral)
                - match(plan, result.salary, result.deferral)) >= 1


def test_certify_against_brute_force_at_boundaries():
    rng = random.Random(2026)
    for _ in range(6):
        plan = random_plan(rng)
        for s_min, s_max in ((MIN_SALARY_CENTS, MIN_SALARY_CENTS + 8),
                             (MAX_SALARY_CENTS - 8, MAX_SALARY_CENTS)):
            expected = brute_force_min_counterexample(plan, s_min, s_max)
            result = certify(plan, s_min, s_max)
            if expected is None:
                assert result.passed, f"误报反例: {plan} {result}"
            else:
                assert not result.passed
                assert (result.salary, result.deferral) == expected
