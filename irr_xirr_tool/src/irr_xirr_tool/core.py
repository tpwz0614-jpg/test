"""Core financial math: NPV/XNPV, IRR/XIRR (with multi-root detection), MIRR, payback period.

Pure-stdlib by design (no numpy/scipy) so it stays trivially embeddable as a library.
Root finding uses grid-scan + bisection, per spec, to avoid the single-Newton-guess
initial-value dependency that both Excel's own IRR() and numpy_financial.irr() suffer from.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

DAYS_PER_YEAR = 365.0

# Default search domain for IRR/XIRR root scanning, as a rate (0.5 == 50%).
# Rate must be > -1 (a discount factor of 0 or negative is not economically
# meaningful and breaks fractional-exponent XIRR math).
DEFAULT_LO = -0.999999
DEFAULT_HI = 10.0  # 1000%
DEFAULT_SCAN_POINTS = 100_000
BISECTION_TOL = 1e-12
BISECTION_MAX_ITER = 200


class InvalidCashFlowError(ValueError):
    """Raised when the cash-flow series cannot possibly have an IRR/XIRR/MIRR."""


@dataclass
class RootSearchResult:
    """Outcome of scanning for real roots of an NPV(rate)=0 style equation."""

    roots: List[float] = field(default_factory=list)
    status: str = "none"  # "unique" | "multiple" | "none"
    search_lo: float = DEFAULT_LO
    search_hi: float = DEFAULT_HI
    message: str = ""

    @property
    def rate(self) -> Optional[float]:
        """The single rate, if unique. None otherwise (see .roots / .status)."""
        return self.roots[0] if self.status == "unique" else None


@dataclass
class PaybackResult:
    periods: Optional[float]  # fractional periods (or fractional years for dated CF)
    message: str


def _validate_signs(amounts: Sequence[float], label: str = "cash flows") -> None:
    if len(amounts) < 2:
        raise InvalidCashFlowError(f"{label}: need at least 2 cash flows.")
    has_pos = any(a > 0 for a in amounts)
    has_neg = any(a < 0 for a in amounts)
    if not (has_pos and has_neg):
        raise InvalidCashFlowError(
            f"{label}: all cash flows have the same sign (or are zero); "
            "no finite rate of return can satisfy NPV=0. "
            "A valid series needs at least one negative (outflow) and one positive (inflow) value."
        )


def npv(rate: float, amounts: Sequence[float]) -> float:
    """NPV using the same convention as irr(): amounts[0] is undiscounted (t=0).

    This differs from Excel's worksheet NPV() function, which discounts its
    first argument by one period. This convention is chosen so that
    npv(irr(amounts), amounts) == 0, matching the IRR definition.
    """
    if rate <= -1:
        raise ValueError("rate must be > -1")
    return sum(a / (1.0 + rate) ** i for i, a in enumerate(amounts))


def xnpv(rate: float, amounts: Sequence[float], dates: Sequence[_dt.date]) -> float:
    """Excel-compatible XNPV: actual/365 day-count from the first date."""
    if rate <= -1:
        raise ValueError("rate must be > -1")
    if len(amounts) != len(dates):
        raise ValueError("amounts and dates must be the same length")
    d0 = dates[0]
    return sum(
        a / (1.0 + rate) ** ((d - d0).days / DAYS_PER_YEAR)
        for a, d in zip(amounts, dates)
    )


def _bisect(f: Callable[[float], float], a: float, b: float,
            tol: float = BISECTION_TOL, max_iter: int = BISECTION_MAX_ITER) -> float:
    fa, fb = f(a), f(b)
    if fa == 0:
        return a
    if fb == 0:
        return b
    if (fa < 0) == (fb < 0):
        raise ValueError("f(a) and f(b) must have opposite signs")
    for _ in range(max_iter):
        m = (a + b) / 2.0
        fm = f(m)
        if fm == 0 or (b - a) / 2.0 < tol:
            return m
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b, fb = m, fm
    return (a + b) / 2.0


def _scan_for_roots(
    f: Callable[[float], float],
    lo: float,
    hi: float,
    n_points: int,
) -> List[float]:
    """Bracket sign changes on a uniform grid over (lo, hi), then bisect each bracket."""
    step = (hi - lo) / n_points
    xs = [lo + i * step for i in range(n_points + 1)]
    roots: List[float] = []
    prev_x = xs[0]
    prev_f = f(prev_x)
    if prev_f == 0:
        roots.append(prev_x)
    for x in xs[1:]:
        fx = f(x)
        if fx == 0:
            roots.append(x)
        elif (prev_f < 0) != (fx < 0):
            root = _bisect(f, prev_x, x)
            # de-dup roots that land extremely close together (grid straddling a near-tangent)
            if not roots or abs(root - roots[-1]) > 1e-9:
                roots.append(root)
        prev_x, prev_f = x, fx
    return roots


def _find_roots(
    f: Callable[[float], float],
    lo: float = DEFAULT_LO,
    hi: float = DEFAULT_HI,
    n_points: int = DEFAULT_SCAN_POINTS,
) -> RootSearchResult:
    roots = _scan_for_roots(f, lo, hi, n_points)
    if not roots:
        return RootSearchResult(
            roots=[], status="none", search_lo=lo, search_hi=hi,
            message=(
                f"No real solution found in the searched range "
                f"[{lo:.4%}, {hi:.4%}]. Try widening the search range if you "
                "believe a valid rate exists outside it."
            ),
        )
    if len(roots) == 1:
        return RootSearchResult(
            roots=roots, status="unique", search_lo=lo, search_hi=hi,
            message="Unique real solution found.",
        )
    return RootSearchResult(
        roots=sorted(roots), status="multiple", search_lo=lo, search_hi=hi,
        message=(
            f"{len(roots)} real solutions found in range "
            f"[{lo:.4%}, {hi:.4%}]: "
            + ", ".join(f"{r:.4%}" for r in sorted(roots))
            + ". The cash-flow series changes sign more than once, so the "
            "internal rate of return is not unique; pick the economically "
            "meaningful one."
        ),
    )


def irr(
    amounts: Sequence[float],
    lo: float = DEFAULT_LO,
    hi: float = DEFAULT_HI,
    n_points: int = DEFAULT_SCAN_POINTS,
) -> RootSearchResult:
    """IRR for equally-spaced (e.g. annual) cash flows, Excel IRR()-compatible.

    amounts[0] is the cash flow at t=0 (typically the negative initial outlay),
    amounts[i] at period i.
    """
    amounts = list(amounts)
    _validate_signs(amounts, "cash flows")
    return _find_roots(lambda r: npv(r, amounts), lo, hi, n_points)


def xirr(
    amounts: Sequence[float],
    dates: Sequence[_dt.date],
    lo: float = DEFAULT_LO,
    hi: float = DEFAULT_HI,
    n_points: int = DEFAULT_SCAN_POINTS,
) -> RootSearchResult:
    """XIRR for irregularly-dated cash flows, Excel XIRR()-compatible (actual/365)."""
    amounts = list(amounts)
    dates = list(dates)
    if len(amounts) != len(dates):
        raise ValueError("amounts and dates must be the same length")
    _validate_signs(amounts, "cash flows")
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    sorted_dates = [dates[i] for i in order]
    sorted_amounts = [amounts[i] for i in order]
    return _find_roots(lambda r: xnpv(r, sorted_amounts, sorted_dates), lo, hi, n_points)


def mirr(amounts: Sequence[float], finance_rate: float, reinvest_rate: float) -> float:
    """MIRR for equally-spaced cash flows, Excel MIRR()-compatible.

    Negative cash flows are discounted to t=0 at finance_rate; positive cash
    flows are compounded to the final period at reinvest_rate.
    """
    amounts = list(amounts)
    _validate_signs(amounts, "cash flows")
    n = len(amounts) - 1
    pv_negative = sum(
        a / (1.0 + finance_rate) ** i for i, a in enumerate(amounts) if a < 0
    )
    fv_positive = sum(
        a * (1.0 + reinvest_rate) ** (n - i) for i, a in enumerate(amounts) if a > 0
    )
    if pv_negative == 0 or fv_positive == 0:
        raise InvalidCashFlowError("MIRR requires both outflows and inflows.")
    return (fv_positive / -pv_negative) ** (1.0 / n) - 1.0


def xmirr(
    amounts: Sequence[float],
    dates: Sequence[_dt.date],
    finance_rate: float,
    reinvest_rate: float,
) -> float:
    """Date-based MIRR extension (actual/365). NOT an Excel-native function

    (Excel has no XMIRR) — provided for irregularly-dated series, but not
    verified against an Excel formula since none exists.
    """
    amounts = list(amounts)
    dates = list(dates)
    if len(amounts) != len(dates):
        raise ValueError("amounts and dates must be the same length")
    _validate_signs(amounts, "cash flows")
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    sorted_dates = [dates[i] for i in order]
    sorted_amounts = [amounts[i] for i in order]
    d0, dn = sorted_dates[0], sorted_dates[-1]
    years = (dn - d0).days / DAYS_PER_YEAR
    if years <= 0:
        raise InvalidCashFlowError("XMIRR requires cash flows spanning more than one day.")
    pv_negative = sum(
        a / (1.0 + finance_rate) ** ((d - d0).days / DAYS_PER_YEAR)
        for a, d in zip(sorted_amounts, sorted_dates) if a < 0
    )
    fv_positive = sum(
        a * (1.0 + reinvest_rate) ** ((dn - d).days / DAYS_PER_YEAR)
        for a, d in zip(sorted_amounts, sorted_dates) if a > 0
    )
    if pv_negative == 0 or fv_positive == 0:
        raise InvalidCashFlowError("XMIRR requires both outflows and inflows.")
    return (fv_positive / -pv_negative) ** (1.0 / years) - 1.0


def payback_period(amounts: Sequence[float]) -> PaybackResult:
    """Simple (non-discounted) payback period in periods, linearly interpolated."""
    amounts = list(amounts)
    cumulative = 0.0
    prev_cumulative = 0.0
    for i, a in enumerate(amounts):
        prev_cumulative = cumulative
        cumulative += a
        if cumulative >= 0 and i > 0:
            # crossed from negative to >=0 during period i
            fraction = -prev_cumulative / a if a != 0 else 0.0
            return PaybackResult(periods=(i - 1) + fraction, message="Recovered.")
        if cumulative >= 0 and i == 0:
            return PaybackResult(periods=0.0, message="Recovered immediately at t=0.")
    return PaybackResult(
        periods=None,
        message="Cash flows never recover the initial investment within the given series.",
    )


def payback_period_dates(
    amounts: Sequence[float], dates: Sequence[_dt.date]
) -> PaybackResult:
    """Simple payback period in years (actual/365) for irregularly-dated cash flows."""
    amounts = list(amounts)
    dates = list(dates)
    order = sorted(range(len(dates)), key=lambda i: dates[i])
    sorted_dates = [dates[i] for i in order]
    sorted_amounts = [amounts[i] for i in order]
    d0 = sorted_dates[0]
    cumulative = 0.0
    prev_cumulative = 0.0
    prev_years = 0.0
    for i, (a, d) in enumerate(zip(sorted_amounts, sorted_dates)):
        years = (d - d0).days / DAYS_PER_YEAR
        prev_cumulative = cumulative
        cumulative += a
        if cumulative >= 0 and i > 0:
            fraction = (-prev_cumulative / a) * (years - prev_years) if a != 0 else 0.0
            return PaybackResult(periods=prev_years + fraction, message="Recovered.")
        if cumulative >= 0 and i == 0:
            return PaybackResult(periods=0.0, message="Recovered immediately at t=0.")
        prev_years = years
    return PaybackResult(
        periods=None,
        message="Cash flows never recover the initial investment within the given series.",
    )
