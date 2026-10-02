"""Certification that an enhanced formula never pays less than the basic one.

Approach
--------
For a fixed salary, both the enhanced amount E(d) and the basic amount
B(d) are closed-form functions of the deferral d.  Their difference
f(d) = B(d) - E(d) is a walk with increments in {-1, 0, +1}: within a
segment between two consecutive deferral breakpoints exactly one enhanced
tier and one basic tier are "filling", and each contributes a periodic
0/1 increment.  The first bad deferral is the first d with f(d) >= 1,
found per segment with O(period) prefix analysis.

The salary domain is scanned over maximal intervals on which every
tier threshold (floor of a bps fraction of salary) is constant; inside
such an interval the bad-deferral set is fixed, so the minimal candidate
salary is max(interval_start, 10 * d_star) because the legal deferral
ceiling is floor(salary / 10).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd
from typing import List, Optional, Sequence

from .match import match
from .plan import (
    BPS_DENOMINATOR,
    MAX_SALARY_CENTS,
    MIN_SALARY_CENTS,
    Plan,
    basic_plan,
)

_M = BPS_DENOMINATOR
_HALF = _M // 2
_BASIC_T1_BPS = 300
_BASIC_T2_BPS = 500
_BASIC_R1 = 10000
_BASIC_R2 = 5000

_BASIC_PLAN = basic_plan()


@dataclass(frozen=True)
class Counterexample:
    salary: int
    deferral: int
    plan_amount: int
    basic_amount: int


@dataclass(frozen=True)
class CertifyResult:
    ok: bool
    counterexample: Optional[Counterexample] = None


def _lcm(a: int, b: int) -> int:
    return a // gcd(a, b) * b


def _segment_hit(
    f_lo: int,
    gam: int,
    ts: int,
    alp: int,
    uprev: int,
    lo: int,
    hi: Optional[int],
) -> Optional[int]:
    """First d in (lo, hi] (hi=None means +inf) with f(d) >= 1.

    On this segment f(d) = const + G(d) - A(d) with
    G(d) = (gam*(d-ts)+HALF)//M and A(d) = (alp*(d-uprev)+HALF)//M.
    f(lo) == f_lo < 1 is a precondition.  Increments are periodic with
    period P; one period is scanned directly, then the trend decides.
    """
    pg = _M // gcd(gam, _M) if gam else 1
    pa = _M // gcd(alp, _M) if alp else 1
    period = _lcm(pg, pa)
    net = (gam - alp) * period // _M

    limit = period if hi is None else min(period, hi - lo)
    f = f_lo
    t = 1
    while t <= limit:
        d = lo + t
        inc = 0
        if gam and (gam * (d - ts) + _HALF) % _M < gam:
            inc += 1
        if alp and (alp * (d - uprev) + _HALF) % _M < alp:
            inc -= 1
        f += inc
        if f >= 1:
            return d
        t += 1

    if hi is not None and hi - lo <= period:
        return None
    if net <= 0:
        return None

    # net > 0: later periods rise; locate the first hitting period.
    pref = 0
    max_pref = 0
    for t in range(1, period + 1):
        d = lo + t
        if gam and (gam * (d - ts) + _HALF) % _M < gam:
            pref += 1
        if alp and (alp * (d - uprev) + _HALF) % _M < alp:
            pref -= 1
        if pref > max_pref:
            max_pref = pref
    j = (1 - f_lo - max_pref + net - 1) // net
    if j < 1:
        j = 1
    target = 1 - f_lo - j * net
    t = 0
    if target > 0:
        pref = 0
        for t in range(1, period + 1):
            d = lo + t
            if gam and (gam * (d - ts) + _HALF) % _M < gam:
                pref += 1
            if alp and (alp * (d - uprev) + _HALF) % _M < alp:
                pref -= 1
            if pref >= target:
                break
    d = lo + j * period + t
    if hi is not None and d > hi:
        return None
    return d


def _first_bad_deferral(
    us: Sequence[int],
    rs: Sequence[int],
    cap: Optional[int],
    t1: int,
    t2: int,
) -> Optional[int]:
    """Minimal d >= 0 with E(d) < B(d) for one threshold configuration."""
    n = len(us)

    # Cap crossing point: first d with the uncapped enhanced sum >= cap.
    dc: Optional[int] = None
    if cap is not None:
        done = 0
        prev = 0
        for i in range(n):
            width = us[i] - prev
            full = (width * rs[i] + _HALF) // _M
            if done + full >= cap:
                need = cap - done
                if rs[i] == 0:
                    dc = prev
                else:
                    x = (need * _M - _HALF + rs[i] - 1) // rs[i]
                    dc = prev + (x if x > 0 else 0)
                break
            done += full
            prev = us[i]
        else:
            if done >= cap:
                dc = prev

    bps = {0, t1, t2}
    bps.update(us)
    if dc is not None:
        bps.add(dc)
    points = sorted(bps)

    # Completed enhanced tiers contribution, advanced as segments move.
    ce = 0
    ptr = 0
    count = len(points)
    for j in range(count):
        lo = points[j]
        hi = points[j + 1] - 1 if j + 1 < count else None

        while ptr < n and us[ptr] <= lo:
            prev_u = us[ptr - 1] if ptr else 0
            ce += ((us[ptr] - prev_u) * rs[ptr] + _HALF) // _M
            ptr += 1
        if ptr < n:
            alp = rs[ptr]
            uprev = us[ptr - 1] if ptr else 0
        else:
            alp = 0
            uprev = 0

        if lo < t1:
            gam, ts, cb = _BASIC_R1, 0, 0
        elif lo < t2:
            gam, ts, cb = _BASIC_R2, t1, t1
        else:
            gam, ts = 0, 0
            cb = t1 + ((t2 - t1) * _BASIC_R2 + _HALF) // _M

        saturated = dc is not None and lo >= dc
        e_lo = cap if saturated else ce + (alp * (lo - uprev) + _HALF) // _M
        f_lo = cb + (gam * (lo - ts) + _HALF) // _M - e_lo
        if f_lo >= 1:
            return lo

        alp_eff = 0 if saturated else alp
        hit = _segment_hit(f_lo, gam, ts, alp_eff, uprev, lo, hi)
        if hit is not None:
            return hit
    return None


def certify(plan: Plan, salary_min: int, salary_max: int) -> CertifyResult:
    """Decide whether ``plan`` pays at least the basic formula everywhere.

    Returns CertifyResult(ok=True) on success, otherwise the
    lexicographically smallest counterexample (minimal salary, then
    minimal deferral at that salary).
    """
    if not (MIN_SALARY_CENTS <= salary_min <= salary_max <= MAX_SALARY_CENTS):
        raise ValueError("salary interval out of legal range")

    ps = [tier.threshold_bps for tier in plan.tiers]
    rs = [tier.rate_bps for tier in plan.tiers]
    cap = plan.cap_cents
    event_ps = [p for p in ps if p > 0] + [_BASIC_T1_BPS, _BASIC_T2_BPS]

    s = salary_min
    while s <= salary_max:
        us: List[int] = [p * s // _M for p in ps]
        t1 = _BASIC_T1_BPS * s // _M
        t2 = _BASIC_T2_BPS * s // _M
        d_star = _first_bad_deferral(us, rs, cap, t1, t2)

        sn = salary_max + 1
        for p in event_ps:
            nxt = ((p * s // _M + 1) * _M + p - 1) // p
            if nxt < sn:
                sn = nxt

        if d_star is not None:
            cand = 10 * d_star
            if cand < s:
                cand = s
            if cand < sn:
                return CertifyResult(
                    ok=False,
                    counterexample=Counterexample(
                        salary=cand,
                        deferral=d_star,
                        plan_amount=match(plan, cand, d_star),
                        basic_amount=match(_BASIC_PLAN, cand, d_star),
                    ),
                )
        s = sn
    return CertifyResult(ok=True)
