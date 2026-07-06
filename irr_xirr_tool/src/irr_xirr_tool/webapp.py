"""Flask web app: manual entry / CSV upload / Excel upload -> IRR/XIRR/NPV/MIRR/payback report."""
from __future__ import annotations

from typing import Optional

from flask import Flask, render_template, request

from . import core, io as cfio, report as reportmod


def _parse_optional_pct(s: Optional[str]) -> Optional[float]:
    if s is None or s.strip() == "":
        return None
    return float(s) / 100.0


_DEFAULT_MANUAL_ROWS = [
    {"date": "", "amount": str(v)}
    for v in (-1_000_000, 300_000, 300_000, 300_000, 300_000, 300_000)
]


def _extract_manual_rows(form) -> list:
    amounts = form.getlist("amount[]") if hasattr(form, "getlist") else []
    dates = form.getlist("date[]") if hasattr(form, "getlist") else []
    if not amounts:
        return []
    return [
        {"date": dates[i] if i < len(dates) else "", "amount": a}
        for i, a in enumerate(amounts)
    ]


def _template_context(form, report=None, error=None) -> dict:
    input_type = form.get("input_type", "manual")
    manual_mode = form.get("manual_mode", "irr")
    manual_rows = _extract_manual_rows(form) if input_type == "manual" else []
    if not manual_rows:
        manual_rows = _DEFAULT_MANUAL_ROWS
    return {
        "report": report,
        "error": error,
        "form": form,
        "input_type": input_type,
        "manual_mode": manual_mode,
        "manual_rows": manual_rows,
    }


def _load_series_from_request(req) -> cfio.CashFlowSeries:
    input_type = req.form.get("input_type", "manual")

    if input_type == "csv":
        f = req.files.get("file")
        if not f or f.filename == "":
            raise ValueError("CSVファイルを選択してください。")
        return cfio.read_csv(f.stream)

    if input_type == "excel":
        f = req.files.get("file")
        if not f or f.filename == "":
            raise ValueError("Excelファイルを選択してください。")
        return cfio.read_excel(f.stream)

    manual_mode = req.form.get("manual_mode", "irr")
    amounts_raw = req.form.getlist("amount[]")
    if manual_mode == "xirr":
        dates_raw = req.form.getlist("date[]")
        pairs = [
            (d, a) for d, a in zip(dates_raw, amounts_raw)
            if d.strip() != "" or a.strip() != ""
        ]
        if not pairs:
            raise ValueError("キャッシュフローを1件以上入力してください。")
        return cfio.parse_manual_dated(pairs)

    amounts = [a for a in amounts_raw if a.strip() != ""]
    if not amounts:
        raise ValueError("キャッシュフローを1件以上入力してください。")
    return cfio.parse_manual_amounts(amounts)


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB upload cap

    @app.get("/")
    def index():
        return render_template("index.html", **_template_context({}))

    @app.post("/calculate")
    def calculate():
        report = None
        error = None
        try:
            series = _load_series_from_request(request)
            rate = _parse_optional_pct(request.form.get("rate_pct"))
            finance_rate = _parse_optional_pct(request.form.get("finance_rate_pct")) or rate
            reinvest_rate = _parse_optional_pct(request.form.get("reinvest_rate_pct")) or rate
            report = reportmod.build_report(
                series, rate=rate, finance_rate=finance_rate, reinvest_rate=reinvest_rate
            )
        except (core.InvalidCashFlowError, ValueError) as e:
            error = str(e)
        return render_template("index.html", **_template_context(request.form, report=report, error=error))

    return app


def main() -> None:
    create_app().run(debug=True, host="127.0.0.1", port=5000)


if __name__ == "__main__":
    main()
