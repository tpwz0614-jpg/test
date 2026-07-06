"""Command-line interface for IRR / XIRR / NPV / MIRR / payback-period calculations."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from typing import Optional

from . import core, io as cfio, report as reportmod


def _parse_rate(s: str) -> float:
    s = s.strip()
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    return float(s)


def _parse_amounts_arg(s: str) -> cfio.CashFlowSeries:
    values = [v.strip() for v in s.split(",") if v.strip() != ""]
    return cfio.parse_manual_amounts(values)


def _parse_dated_arg(s: str) -> cfio.CashFlowSeries:
    pairs = []
    for chunk in s.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        date_str, amount_str = chunk.split(":", 1)
        pairs.append((date_str.strip(), amount_str.strip()))
    return cfio.parse_manual_dated(pairs)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="irr-tool",
        description=(
            "Compute IRR/XIRR, NPV, payback period, and MIRR for a cash-flow "
            "series, matching Excel's IRR()/XIRR()/MIRR() semantics."
        ),
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--amounts", metavar="CSV_LIST",
        help="Equally-spaced cash flows, e.g. '-1000000,300000,300000,300000,300000,300000' (-> IRR)",
    )
    src.add_argument(
        "--dated", metavar="DATE:AMOUNT_LIST",
        help="Dated cash flows, e.g. '2020-01-01:-10000,2020-07-01:2750' (-> XIRR)",
    )
    src.add_argument("--csv", metavar="PATH", help="Read cash flows from a CSV file")
    src.add_argument("--excel", metavar="PATH", help="Read cash flows from an Excel file")

    p.add_argument("--sheet", default=0, help="Sheet name or 0-based index for --excel (default: 0)")
    p.add_argument("--rate", type=_parse_rate, default=None,
                    help="Discount rate for NPV, e.g. 0.08 or 8%% (default: none, skip NPV)")
    p.add_argument("--finance-rate", type=_parse_rate, default=None,
                    help="Finance rate for MIRR (default: --rate)")
    p.add_argument("--reinvest-rate", type=_parse_rate, default=None,
                    help="Reinvestment rate for MIRR (default: --rate)")
    p.add_argument("--search-lo", type=_parse_rate, default=core.DEFAULT_LO,
                    help=f"Lower bound of IRR/XIRR search range (default: {core.DEFAULT_LO:.4%})")
    p.add_argument("--search-hi", type=_parse_rate, default=core.DEFAULT_HI,
                    help=f"Upper bound of IRR/XIRR search range (default: {core.DEFAULT_HI:.0%})")
    p.add_argument("--search-points", type=int, default=core.DEFAULT_SCAN_POINTS,
                    help="Number of grid points scanned for sign changes (default: %(default)s)")
    p.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    return p


def _load_series(args: argparse.Namespace) -> cfio.CashFlowSeries:
    if args.amounts is not None:
        return _parse_amounts_arg(args.amounts)
    if args.dated is not None:
        return _parse_dated_arg(args.dated)
    if args.csv is not None:
        return cfio.read_csv(args.csv)
    if args.excel is not None:
        sheet = args.sheet
        try:
            sheet = int(sheet)
        except (TypeError, ValueError):
            pass
        return cfio.read_excel(args.excel, sheet_name=sheet)
    raise AssertionError("unreachable: argparse mutually exclusive group is required")


def _build_report(args: argparse.Namespace, series: cfio.CashFlowSeries) -> dict:
    finance_rate = args.finance_rate if args.finance_rate is not None else args.rate
    reinvest_rate = args.reinvest_rate if args.reinvest_rate is not None else args.rate
    return reportmod.build_report(
        series,
        rate=args.rate,
        finance_rate=finance_rate,
        reinvest_rate=reinvest_rate,
        search_lo=args.search_lo,
        search_hi=args.search_hi,
        search_points=args.search_points,
    )


_VALUE_FLAGS_NEEDING_NORMALIZATION = ("--amounts", "--dated")


def _normalize_argv(argv: list) -> list:
    """Rewrite `--amounts -1000,...` to `--amounts=-1000,...`.

    Without this, argparse treats a value starting with '-' (a negative
    initial cash flow, the common case) as another option flag.
    """
    out = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in _VALUE_FLAGS_NEEDING_NORMALIZATION and i + 1 < len(argv):
            out.append(f"{a}={argv[i + 1]}")
            i += 2
            continue
        out.append(a)
        i += 1
    return out


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    raw_argv = sys.argv[1:] if argv is None else argv
    args = parser.parse_args(_normalize_argv(list(raw_argv)))

    try:
        series = _load_series(args)
        report = _build_report(args, series)
    except (core.InvalidCashFlowError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        sys.stdout.write(reportmod.format_report_text(report))

    return 0 if report["rate_result"]["status"] != "none" else 1


if __name__ == "__main__":
    raise SystemExit(main())
