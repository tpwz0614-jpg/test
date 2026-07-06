import datetime as dt

import pytest

from irr_xirr_tool import core


def pct_close(value: float, expected_pct: float, tol_pct: float = 0.01) -> bool:
    """Compare `value` (decimal rate) to `expected_pct` (in %) within tol_pct percentage points."""
    return abs(value * 100 - expected_pct) < tol_pct


class TestIRR:
    def test_user_spec_example(self):
        # -1,000,000 initial outlay, 5 years of +300,000 -> IRR ~= 15.24% (spec example)
        r = core.irr([-1_000_000, 300_000, 300_000, 300_000, 300_000, 300_000])
        assert r.status == "unique"
        assert pct_close(r.rate, 15.24, tol_pct=0.01)

    def test_ms_docs_example(self):
        # Microsoft Excel IRR() function documentation example: 8.66%
        r = core.irr([-70000, 12000, 15000, 18000, 21000, 26000])
        assert r.status == "unique"
        assert pct_close(r.rate, 8.66, tol_pct=0.01)

    def test_npv_zero_at_irr_root(self):
        amounts = [-1_000_000, 300_000, 300_000, 300_000, 300_000, 300_000]
        r = core.irr(amounts)
        assert abs(core.npv(r.rate, amounts)) < 1e-4

    def test_all_positive_raises(self):
        with pytest.raises(core.InvalidCashFlowError):
            core.irr([1000, 2000, 3000])

    def test_all_negative_raises(self):
        with pytest.raises(core.InvalidCashFlowError):
            core.irr([-1000, -2000, -3000])

    def test_too_few_cashflows_raises(self):
        with pytest.raises(core.InvalidCashFlowError):
            core.irr([-1000])

    def test_multiple_roots_detected(self):
        # Classic multi-sign-change series with exact integer roots at 0%, 100%, 200%.
        # -1000 + 6000/(1+r) - 11000/(1+r)^2 + 6000/(1+r)^3 = 0 at r=0,1,2
        r = core.irr([-1000, 6000, -11000, 6000])
        assert r.status == "multiple"
        assert len(r.roots) == 3
        for expected in (0.0, 1.0, 2.0):
            assert any(abs(root - expected) < 1e-6 for root in r.roots)
        assert "multiple" in r.message.lower() or "not unique" in r.message.lower()

    def test_no_real_root_reported_not_raised(self):
        # Two sign changes, but the actual algebraic roots are complex, not real.
        # e.g. -1 + 3x - 3x^2 (in x=1/(1+r)) has discriminant 9-12<0 -> no real IRR.
        r = core.irr([-1, 3, -3])
        assert r.status == "none"
        assert r.roots == []
        assert "no real solution" in r.message.lower()


class TestXIRR:
    def test_ms_docs_example(self):
        # Microsoft Excel XIRR() function documentation example: 37.34%
        dates = [
            dt.date(2008, 1, 1),
            dt.date(2008, 3, 1),
            dt.date(2008, 10, 30),
            dt.date(2009, 2, 15),
            dt.date(2009, 4, 1),
        ]
        amounts = [-10000, 2750, 4250, 3250, 2750]
        r = core.xirr(amounts, dates)
        assert r.status == "unique"
        assert pct_close(r.rate, 37.34, tol_pct=0.01)

    def test_unsorted_dates_same_result(self):
        dates = [
            dt.date(2008, 3, 1),
            dt.date(2008, 1, 1),
            dt.date(2009, 4, 1),
            dt.date(2008, 10, 30),
            dt.date(2009, 2, 15),
        ]
        amounts = [2750, -10000, 2750, 4250, 3250]
        r = core.xirr(amounts, dates)
        assert r.status == "unique"
        assert pct_close(r.rate, 37.34, tol_pct=0.01)

    def test_xnpv_zero_at_xirr_root(self):
        dates = [dt.date(2020, 1, 1), dt.date(2020, 7, 1), dt.date(2021, 1, 1)]
        amounts = [-1000, 400, 700]
        r = core.xirr(amounts, dates)
        assert abs(core.xnpv(r.rate, amounts, dates)) < 1e-3

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError):
            core.xirr([-1000, 500], [dt.date(2020, 1, 1)])


class TestMIRR:
    def test_ms_docs_example(self):
        # Microsoft Excel MIRR() function documentation example: 12.61%
        amounts = [-120000, 39000, 30000, 21000, 37000, 46000]
        m = core.mirr(amounts, finance_rate=0.10, reinvest_rate=0.12)
        assert pct_close(m, 12.61, tol_pct=0.01)

    def test_requires_mixed_signs(self):
        with pytest.raises(core.InvalidCashFlowError):
            core.mirr([1000, 2000, 3000], 0.1, 0.1)


class TestPayback:
    def test_simple_interpolated_payback(self):
        # -1000, then +400/yr: cumulative -600,-200,+200 -> recovers between yr2 and yr3
        result = core.payback_period([-1000, 400, 400, 400])
        assert result.periods == pytest.approx(2.5, abs=1e-9)

    def test_never_recovers(self):
        result = core.payback_period([-1000, 100, 100])
        assert result.periods is None
        assert "never recover" in result.message.lower()

    def test_immediate_recovery_at_t0(self):
        result = core.payback_period([1000, -400])
        assert result.periods == 0.0

    def test_dates_payback(self):
        dates = [dt.date(2020, 1, 1), dt.date(2021, 1, 1), dt.date(2022, 1, 1), dt.date(2023, 1, 1)]
        amounts = [-1000, 400, 400, 400]
        result = core.payback_period_dates(amounts, dates)
        assert result.periods == pytest.approx(2.5, abs=1e-2)
