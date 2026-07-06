"""Shared report-building logic used by both the CLI and the web app."""
from __future__ import annotations

from typing import Optional

from . import core
from .io import CashFlowSeries


def build_report(
    series: CashFlowSeries,
    rate: Optional[float] = None,
    finance_rate: Optional[float] = None,
    reinvest_rate: Optional[float] = None,
    search_lo: float = core.DEFAULT_LO,
    search_hi: float = core.DEFAULT_HI,
    search_points: int = core.DEFAULT_SCAN_POINTS,
) -> dict:
    report: dict = {"mode": "xirr" if series.is_dated else "irr", "n_cashflows": len(series.amounts)}

    if series.is_dated:
        root_result = core.xirr(series.amounts, series.dates, lo=search_lo, hi=search_hi, n_points=search_points)
        payback = core.payback_period_dates(series.amounts, series.dates)
    else:
        root_result = core.irr(series.amounts, lo=search_lo, hi=search_hi, n_points=search_points)
        payback = core.payback_period(series.amounts)

    report["rate_result"] = {
        "status": root_result.status,
        "roots": root_result.roots,
        "message": root_result.message,
        "search_lo": root_result.search_lo,
        "search_hi": root_result.search_hi,
    }
    report["payback"] = {"periods": payback.periods, "message": payback.message}

    if rate is not None:
        if series.is_dated:
            report["npv"] = {"rate": rate, "value": core.xnpv(rate, series.amounts, series.dates)}
        else:
            report["npv"] = {"rate": rate, "value": core.npv(rate, series.amounts)}

    if finance_rate is not None and reinvest_rate is not None:
        try:
            if series.is_dated:
                mirr_value = core.xmirr(series.amounts, series.dates, finance_rate, reinvest_rate)
            else:
                mirr_value = core.mirr(series.amounts, finance_rate, reinvest_rate)
            report["mirr"] = {
                "finance_rate": finance_rate,
                "reinvest_rate": reinvest_rate,
                "value": mirr_value,
                "is_extension": series.is_dated,
            }
        except core.InvalidCashFlowError as e:
            report["mirr"] = {"error": str(e)}

    return report


def format_report_text(report: dict) -> str:
    lines = []
    mode_label = "XIRR (dated cash flows)" if report["mode"] == "xirr" else "IRR (equally-spaced cash flows)"
    lines.append(f"Mode: {mode_label}  |  {report['n_cashflows']} cash flows")
    lines.append("")

    rr = report["rate_result"]
    label = "XIRR" if report["mode"] == "xirr" else "IRR"
    if rr["status"] == "unique":
        lines.append(f"{label}: {rr['roots'][0]:.4%}")
    elif rr["status"] == "multiple":
        lines.append(f"{label}: MULTIPLE SOLUTIONS FOUND")
        for r in rr["roots"]:
            lines.append(f"  - {r:.4%}")
    else:
        lines.append(f"{label}: NO REAL SOLUTION FOUND")
    lines.append(f"  {rr['message']}")
    lines.append("")

    pb = report["payback"]
    if pb["periods"] is None:
        lines.append(f"Payback period: not recovered ({pb['message']})")
    elif report["mode"] == "xirr":
        lines.append(f"Payback period: {pb['periods']:.3f} years")
    else:
        lines.append(f"Payback period: {pb['periods']:.3f} periods")
    lines.append("")

    if "npv" in report:
        lines.append(f"NPV @ {report['npv']['rate']:.4%}: {report['npv']['value']:,.2f}")
        lines.append("")

    if "mirr" in report:
        if "error" in report["mirr"]:
            lines.append(f"MIRR: unavailable ({report['mirr']['error']})")
        else:
            m = report["mirr"]
            extra = "  [extension, not an Excel-native function]" if m["is_extension"] else ""
            lines.append(
                f"MIRR (finance={m['finance_rate']:.4%}, reinvest={m['reinvest_rate']:.4%}): "
                f"{m['value']:.4%}{extra}"
            )
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
