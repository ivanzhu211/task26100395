"""增强公式合格性判定。

判定思路（全程整数/有理数精确运算）：

对固定工资 s，设 B(s,d) 为基础公式配比、E_raw(s,d) 为增强公式未加年度上限的
配比、C 为年度上限，则少付当且仅当

    B(s,d) >= min(E_raw(s,d), C) + 1
        <=>  B(s,d) >= E_raw(s,d) + 1   或   B(s,d) >= C + 1

两部分分别处理：

1. 上限条件 B >= C+1：B 关于 d 单调不减，最小缴费有闭式解；B_max(s) 关于 s
   单调不减，最小工资可二分。
2. 逐档条件 B >= E_raw+1：把基础公式档位边界 {300,500} 与增强公式档位边界
   合并，d 轴被切成固定顺序的若干段。每段内 B 与 E_raw 都是"向下取整的线性
   函数"，段内最小可行 d 有闭式解（含对数锯齿段的丢番图分析）。再用
   "精确赤字 >= 1/2" 的必要条件（B <= B_exact + 1/2，E_raw >= E_exact）
   过滤掉不可能产生反例的 (段, 工资区间)，只对幸存区间做向量化扫描。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction

import numpy as np

from .core import (
    BASIS_POINTS as BP,
    HALF_BASIS_POINTS as HALF,
    MAX_SALARY_CENTS,
    MIN_SALARY_CENTS,
    BASIC_PLAN,
    Plan,
    match,
)

_B1_BP = 300
_B2_BP = 500
_DMAX_BP = 1000
_CHUNK = 1_000_000
_INF = 1 << 62


@dataclass(frozen=True)
class Certification:
    passed: bool
    salary: int | None = None
    deferral: int | None = None


@dataclass(frozen=True)
class _Segment:
    lo_bp: int
    hi_bp: int
    is_first: bool
    beta: int  # 基础公式在该段的边际率：10000 / 5000 / 0
    r: int  # 增强公式当前档匹配率（越过末档为 0）
    ce_bp: int  # 当前档累计阈值（基点）
    full: tuple[tuple[int, int], ...]  # 已填满的档：(threshold_bp, rate_bp)


def _basic_max(salary: int) -> int:
    b1 = salary * _B1_BP // BP
    b2 = salary * _B2_BP // BP
    return b1 + (b2 - b1 + 1) // 2


def _build_segments(plan: Plan) -> list[_Segment]:
    bps = sorted({_B1_BP, _B2_BP, _DMAX_BP} | {t.threshold_bp for t in plan.tiers})
    segments: list[_Segment] = []
    prev_bp: int | None = None
    for hi_bp in bps:
        lo_bp = prev_bp if prev_bp is not None else 0
        is_first = prev_bp is None
        prev_bp = hi_bp
        if hi_bp == lo_bp:
            continue
        if hi_bp <= _B1_BP:
            beta = BP
        elif lo_bp >= _B2_BP:
            beta = 0
        else:
            beta = 5000
        count = sum(1 for t in plan.tiers if t.threshold_bp <= lo_bp)
        full = tuple((t.threshold_bp, t.rate_bp) for t in plan.tiers[:count])
        if count < len(plan.tiers):
            r = plan.tiers[count].rate_bp
            ce_bp = plan.tiers[count - 1].threshold_bp if count else 0
        else:
            r = 0
            ce_bp = 0
        segments.append(_Segment(lo_bp, hi_bp, is_first, beta, r, ce_bp, full))
    return segments


def _filter_window(seg: _Segment, s_min: int, s_max: int) -> tuple[int, int] | None:
    """必要条件 delta_exact >= 1/2 给出的工资区间；None 表示整段可排除。"""
    a = Fraction(0)
    c = Fraction(0)
    w = Fraction(0)

    def add_floor(coeff: Fraction, bp: int) -> None:
        nonlocal a, w
        a += coeff * bp / BP
        if coeff < 0:
            w += -coeff

    beta_ex = {BP: Fraction(1), 5000: Fraction(1, 2), 0: Fraction(0)}[seg.beta]
    if seg.beta == 5000:
        add_floor(Fraction(1, 2), _B1_BP)
    elif seg.beta == 0:
        add_floor(Fraction(1, 2), _B1_BP)
        add_floor(Fraction(1, 2), _B2_BP)
    prev_bp = 0
    for t_j, r_j in seg.full:
        add_floor(Fraction(-r_j, BP), t_j)
        add_floor(Fraction(r_j, BP), prev_bp)
        prev_bp = t_j
    add_floor(Fraction(seg.r, BP), seg.ce_bp)
    slope_d = beta_ex - Fraction(seg.r, BP)
    if slope_d > 0:
        add_floor(slope_d, seg.hi_bp)
    else:
        add_floor(slope_d, seg.lo_bp)
        c += slope_d
    rhs = Fraction(1, 2) - w - c
    if a > 0:
        lo = math.ceil(rhs / a)
        hi = s_max
        lo = max(lo, s_min)
    elif a < 0:
        lo = s_min
        hi = min(math.floor(rhs / a), s_max)
    else:
        if Fraction(0) >= rhs:
            lo, hi = s_min, s_max
        else:
            return None
    if lo > hi:
        return None
    return lo, hi


def _ceil_div_arr(a: np.ndarray, b: int) -> np.ndarray:
    return -((-a) // b)


def _vec_basic(s: np.ndarray, d: np.ndarray) -> np.ndarray:
    b1 = s * _B1_BP // BP
    b2 = s * _B2_BP // BP
    a1 = np.minimum(d, b1)
    a2 = np.clip(d - b1, 0, b2 - b1)
    return a1 + (a2 * 5000 + HALF) // BP


def _vec_plan(plan: Plan, s: np.ndarray, d: np.ndarray) -> np.ndarray:
    total = np.zeros_like(d)
    prev = np.zeros_like(d)
    for tier in plan.tiers:
        c = s * tier.threshold_bp // BP
        amount = np.clip(d - prev, 0, c - prev)
        total += (amount * tier.rate_bp + HALF) // BP
        prev = c
    if plan.cap_cents is not None:
        total = np.minimum(total, plan.cap_cents)
    return total


def _segment_candidates(
    plan: Plan, seg: _Segment, s: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """对工资数组 s，返回该段内最小可行缴费 d 及有效标记（逐档条件）。"""
    lo_d = np.zeros_like(s) if seg.is_first else s * seg.lo_bp // BP + 1
    hi_d = s * seg.hi_bp // BP
    b1 = s * _B1_BP // BP
    b2 = s * _B2_BP // BP
    e0 = np.zeros_like(s)
    prev = np.zeros_like(s)
    for t_j, r_j in seg.full:
        c_j = s * t_j // BP
        e0 += ((c_j - prev) * r_j + HALF) // BP
        prev = c_j
    ce = s * seg.ce_bp // BP
    r = seg.r
    ones = np.ones_like(s, dtype=bool)
    if seg.beta == BP:
        if r == BP:
            d = lo_d
            valid = (ce - e0) >= 1
        else:
            d = (BP * e0 - r * ce + HALF) // (BP - r) + 1
            d = np.maximum(d, lo_d)
            valid = ones
    elif seg.beta == 5000:
        m = e0 + 1 - b1
        p = 1 - b1
        if r == 0:
            d = np.maximum(2 * m - p, lo_d)
            valid = ones
        elif r == BP:
            upper = p - 2 * m + 2 * ce
            d = lo_d
            valid = lo_d <= upper
        else:
            q = HALF - r * ce
            j0 = (r * lo_d + q) // BP
            js = [j0 - 1, j0, j0 + 1]
            if r < 5000:
                jstar = _ceil_div_arr(q + r * (2 * m - p + 1) - BP, BP - 2 * r)
                js += [jstar - 2, jstar - 1, jstar, jstar + 1, jstar + 2]
            best = np.full_like(s, _INF)
            for j in js:
                left = _ceil_div_arr(BP * j - q, r)
                right = _ceil_div_arr(BP * (j + 1) - q, r) - 1
                thresh = 2 * (m + j) - p
                cand = np.maximum(np.maximum(left, thresh), lo_d)
                ok = cand <= np.minimum(right, hi_d)
                best = np.where(ok & (cand < best), cand, best)
            d = best
            valid = best < _INF
    else:
        bmax = b1 + (b2 - b1 + 1) // 2
        deficit = bmax - e0 - ((r * (lo_d - ce) + HALF) // BP)
        d = lo_d
        valid = deficit >= 1
    valid &= (d >= lo_d) & (d <= hi_d) & (lo_d <= hi_d)
    d = np.where(valid, d, 0)
    deficit_exact = _vec_basic(s, d) - _vec_plan(plan, s, d)
    valid &= deficit_exact >= 1
    return d, valid


def _scan_segment(
    plan: Plan, seg: _Segment, w_lo: int, w_hi: int
) -> tuple[int, int] | None:
    s = w_lo
    while s <= w_hi:
        e = min(s + _CHUNK - 1, w_hi)
        s_arr = np.arange(s, e + 1, dtype=np.int64)
        d_arr, valid = _segment_candidates(plan, seg, s_arr)
        if valid.any():
            i = int(np.argmax(valid))
            return int(s_arr[i]), int(d_arr[i])
        s = e + 1
    return None


def _segment_min_d_scalar(plan: Plan, seg: _Segment, s: int) -> int | None:
    d_arr, valid = _segment_candidates(plan, seg, np.array([s], dtype=np.int64))
    if not bool(valid[0]):
        return None
    d = int(d_arr[0])
    lo_d = 0 if seg.is_first else s * seg.lo_bp // BP + 1
    hi_d = s * seg.hi_bp // BP

    def deficit(x: int) -> int:
        return match(BASIC_PLAN, s, x) - match(plan, s, x)

    for _ in range(10):
        if d > lo_d and deficit(d - 1) >= 1:
            d -= 1
        elif d <= hi_d and deficit(d) < 1:
            d += 1
        else:
            break
    if lo_d <= d <= hi_d and deficit(d) >= 1:
        return d
    return None


def _cap_min_deferral(cap: int, s: int) -> int | None:
    need = cap + 1
    b1 = s * _B1_BP // BP
    b2 = s * _B2_BP // BP
    if need <= b1:
        return need
    if need <= b1 + (b2 - b1 + 1) // 2:
        return b1 + 2 * (need - b1) - 1
    return None


def _min_salary_with_basic_max(need: int, lo: int, hi: int) -> int | None:
    if _basic_max(hi) < need:
        return None
    while lo < hi:
        mid = (lo + hi) // 2
        if _basic_max(mid) >= need:
            hi = mid
        else:
            lo = mid + 1
    return lo


def certify(plan: Plan, salary_min: int, salary_max: int) -> Certification:
    if not MIN_SALARY_CENTS <= salary_min <= salary_max <= MAX_SALARY_CENTS:
        raise ValueError("工资区间越界或为空")
    candidates: list[tuple[int, int]] = []
    if plan.cap_cents is not None:
        s_cap = _min_salary_with_basic_max(plan.cap_cents + 1, salary_min, salary_max)
        if s_cap is not None:
            d_cap = _cap_min_deferral(plan.cap_cents, s_cap)
            if d_cap is not None:
                candidates.append((s_cap, d_cap))
    segments = _build_segments(plan)
    for seg in segments:
        window = _filter_window(seg, salary_min, salary_max)
        if window is None:
            continue
        hit = _scan_segment(plan, seg, window[0], window[1])
        if hit is not None:
            candidates.append(hit)
    if not candidates:
        return Certification(passed=True)
    s_star = min(s for s, _ in candidates)
    ds: list[int] = []
    if plan.cap_cents is not None:
        d_cap = _cap_min_deferral(plan.cap_cents, s_star)
        if d_cap is not None:
            ds.append(d_cap)
    for seg in segments:
        d = _segment_min_d_scalar(plan, seg, s_star)
        if d is not None:
            ds.append(d)
    d_star = min(ds)
    assert match(BASIC_PLAN, s_star, d_star) - match(plan, s_star, d_star) >= 1
    return Certification(passed=False, salary=s_star, deferral=d_star)
