"""Input loading: manual entry, CSV, and Excel, for both IRR (amount-only) and
XIRR (date + amount) cash-flow series.

CSV/Excel layout:
  - Two columns headered "date" and "amount" (any case) -> XIRR mode.
  - Two columns with no recognizable header and the first column parses as a
    date -> XIRR mode.
  - A single amount column -> IRR mode (row order = period 0, 1, 2, ...).
A header row is optional; it is auto-detected (a row is a header if none of
its non-empty cells parse as a number or a date).
"""
from __future__ import annotations

import csv
import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

CellValue = Union[str, float, int, _dt.date, _dt.datetime, None]


@dataclass
class CashFlowSeries:
    amounts: List[float]
    dates: Optional[List[_dt.date]] = None  # None => equally-spaced (IRR) mode

    @property
    def is_dated(self) -> bool:
        return self.dates is not None


DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y.%m.%d")


def _coerce_float(cell: CellValue) -> Optional[float]:
    if cell is None or isinstance(cell, bool):
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell).strip().replace(",", "").replace("¥", "").replace("$", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _coerce_date(cell: CellValue) -> Optional[_dt.date]:
    if cell is None:
        return None
    if isinstance(cell, _dt.datetime):
        return cell.date()
    if isinstance(cell, _dt.date):
        return cell
    s = str(cell).strip()
    if s == "":
        return None
    for fmt in DATE_FORMATS:
        try:
            return _dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    try:
        return _dt.date.fromisoformat(s)
    except ValueError:
        return None


def _is_headerish(row: Sequence[CellValue]) -> bool:
    for cell in row:
        if cell is None:
            continue
        if isinstance(cell, str) and cell.strip() == "":
            continue
        if _coerce_float(cell) is None and _coerce_date(cell) is None:
            return True
    return False


def _row_is_blank(row: Sequence[CellValue]) -> bool:
    return all(cell is None or (isinstance(cell, str) and cell.strip() == "") for cell in row)


def rows_to_series(rows: Sequence[Sequence[CellValue]]) -> CashFlowSeries:
    rows = [r for r in rows if not _row_is_blank(r)]
    if not rows:
        raise ValueError("No data rows found.")

    header: Optional[List[str]] = None
    data_rows = rows
    if _is_headerish(rows[0]):
        header = [str(c).strip().lower() if c is not None else "" for c in rows[0]]
        data_rows = rows[1:]
    if not data_rows:
        raise ValueError("No data rows found (only a header row was present).")

    ncols = max(len(r) for r in data_rows)
    date_idx: Optional[int]
    amount_idx: int
    dated: bool

    if header and ncols >= 2 and any("date" in h for h in header):
        date_idx = next(i for i, h in enumerate(header) if "date" in h)
        amount_idx = next(
            (i for i, h in enumerate(header) if "amount" in h or "cash" in h or "value" in h),
            1 if date_idx == 0 else 0,
        )
        dated = True
    elif ncols >= 2 and _coerce_date(data_rows[0][0]) is not None:
        date_idx, amount_idx, dated = 0, 1, True
    else:
        date_idx, amount_idx, dated = None, 0, False

    amounts: List[float] = []
    dates: List[_dt.date] = []
    for row_num, row in enumerate(data_rows, start=1):
        amt = _coerce_float(row[amount_idx]) if amount_idx < len(row) else None
        if amt is None:
            raise ValueError(f"Row {row_num}: could not parse an amount from {row!r}")
        amounts.append(amt)
        if dated:
            assert date_idx is not None
            d = _coerce_date(row[date_idx]) if date_idx < len(row) else None
            if d is None:
                raise ValueError(f"Row {row_num}: could not parse a date from {row!r}")
            dates.append(d)

    return CashFlowSeries(amounts=amounts, dates=dates if dated else None)


def parse_manual_amounts(values: Sequence[Union[str, float]]) -> CashFlowSeries:
    """Manual entry, IRR mode: a plain ordered list of cash flow amounts."""
    amounts = []
    for i, v in enumerate(values):
        f = _coerce_float(v)
        if f is None:
            raise ValueError(f"Entry {i + 1}: could not parse amount {v!r}")
        amounts.append(f)
    return CashFlowSeries(amounts=amounts, dates=None)


def parse_manual_dated(pairs: Sequence[Tuple[Union[str, _dt.date], Union[str, float]]]) -> CashFlowSeries:
    """Manual entry, XIRR mode: an ordered list of (date, amount) pairs."""
    amounts, dates = [], []
    for i, (d, a) in enumerate(pairs):
        parsed_date = _coerce_date(d)
        parsed_amount = _coerce_float(a)
        if parsed_date is None:
            raise ValueError(f"Entry {i + 1}: could not parse date {d!r}")
        if parsed_amount is None:
            raise ValueError(f"Entry {i + 1}: could not parse amount {a!r}")
        dates.append(parsed_date)
        amounts.append(parsed_amount)
    return CashFlowSeries(amounts=amounts, dates=dates)


def read_csv(path_or_buffer, encoding: str = "utf-8-sig") -> CashFlowSeries:
    if hasattr(path_or_buffer, "read"):
        text = path_or_buffer.read()
        if isinstance(text, bytes):
            text = text.decode(encoding)
        rows = list(csv.reader(text.splitlines()))
    else:
        with open(path_or_buffer, "r", encoding=encoding, newline="") as f:
            rows = list(csv.reader(f))
    return rows_to_series(rows)


def read_excel(path_or_buffer, sheet_name: Union[int, str] = 0) -> CashFlowSeries:
    import openpyxl

    wb = openpyxl.load_workbook(path_or_buffer, data_only=True, read_only=True)
    ws = wb.worksheets[sheet_name] if isinstance(sheet_name, int) else wb[sheet_name]
    rows = [list(row) for row in ws.iter_rows(values_only=True)]
    return rows_to_series(rows)


def load_cashflows(path: Union[str, Path], sheet_name: Union[int, str] = 0) -> CashFlowSeries:
    """Dispatch on file extension: .csv -> read_csv, .xlsx/.xlsm/.xls -> read_excel."""
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return read_csv(p)
    if suffix in (".xlsx", ".xlsm", ".xls"):
        return read_excel(p, sheet_name=sheet_name)
    raise ValueError(f"Unsupported file type: {suffix} (expected .csv or .xlsx)")
