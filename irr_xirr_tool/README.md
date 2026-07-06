# irr-xirr-tool

設備投資案件の採算評価用 IRR/XIRR 計算ツール。Excel の `IRR()` / `XIRR()` /
`MIRR()` と数値一致する計算コアを、**Python ライブラリ / CLI / Web アプリ**
の3形態で提供します。

## 特徴・実装方針

- **複数解・実数解なしの検出**: 単一の Newton-Raphson（初期値依存の1解のみ返す方式）
  ではなく、探索範囲をグリッドスキャンして符号変化を検出し、各区間を二分法
  (bisection) で追い込む方式を採用。符号変化が複数回あるキャッシュフローでは
  すべての実数解を検出して報告し、実数解が存在しない場合もそれを明示します
  （`irr_xirr_tool.core.RootSearchResult.status` が `"unique" / "multiple" / "none"`）。
- **XIRR は actual/365 の日数ベース**で `(1+rate)^((date-date0)/365)` により割引。
- **全期間同符号など解が存在しえない入力はエラー**として検出
  (`InvalidCashFlowError`)。
- **Excel との数値一致をテストで検証**: Microsoft 公式ドキュメントに掲載されている
  IRR/XIRR/MIRR の例題（`tests/test_core.py`）で一致を確認済み。
  - `IRR([-70000,12000,15000,18000,21000,26000])` = **8.66%**
  - `XIRR([-10000,2750,4250,3250,2750], dates)` = **37.34%**
  - `MIRR([-120000,39000,30000,21000,37000,46000], 10%, 12%)` = **12.61%**
  - 本仕様の例 `IRR([-1000000,300000×5])` = **15.24%**
- コア計算 (`core.py`) は **標準ライブラリのみ**で実装（numpy/scipy 不使用）。
  CSV/Excel 読み込みにのみ `openpyxl` を使用し、Web アプリにのみ `Flask` を使用。

### NPV の定義について（重要な注意）

`core.npv(rate, amounts)` は `amounts[0]`（t=0のキャッシュフロー、通常は初期投資）
を **割引かない**規約です。これは `npv(irr(amounts), amounts) == 0` となる
IRR の定義と整合させるためで、Excel のワークシート関数 `NPV()`（第1引数を
1期目として割り引く仕様）とは異なる規約です。IRR/XIRR/MIRR は Excel の関数と
数値一致しますが、`npv`/`xnpv` は「IRR の定義に整合するNPV」である点にご注意
ください。

### MIRR / XMIRR について

`mirr()` は Excel の `MIRR()` と数値一致する、等間隔キャッシュフロー用の実装です。
`xmirr()` は日付付き（不等間隔）キャッシュフロー向けの拡張ですが、**Excel には
XMIRR に相当する関数が存在しないため、Excel 一致テストの対象外**です
（レポート上も "拡張・Excel非標準" と明示されます）。

## セットアップ

```bash
cd irr_xirr_tool
pip install -e .          # または: pip install -r requirements.txt
pytest                     # テスト実行（Excel一致検証を含む）
```

## 1. Python ライブラリとして使う

```python
import datetime as dt
from irr_xirr_tool import core

# 等間隔（年次）キャッシュフロー -> IRR
result = core.irr([-1_000_000, 300_000, 300_000, 300_000, 300_000, 300_000])
print(result.status)   # "unique" / "multiple" / "none"
print(result.rate)     # 0.15238237... (unique の場合のみ)
print(result.roots)    # [0.15238237...]

# 日付付き（不等間隔）キャッシュフロー -> XIRR
dates = [dt.date(2008,1,1), dt.date(2008,3,1), dt.date(2008,10,30),
         dt.date(2009,2,15), dt.date(2009,4,1)]
amounts = [-10000, 2750, 4250, 3250, 2750]
xr = core.xirr(amounts, dates)

# NPV / XNPV, MIRR, 回収期間
core.npv(0.08, [-1_000_000, 300_000, 300_000, 300_000, 300_000, 300_000])
core.mirr([-120000, 39000, 30000, 21000, 37000, 46000], finance_rate=0.10, reinvest_rate=0.12)
core.payback_period([-1_000_000, 300_000, 300_000, 300_000, 300_000, 300_000])

# 複数解の例
multi = core.irr([-1000, 6000, -11000, 6000])
assert multi.status == "multiple"
print(multi.roots)  # [0.0, 1.0, 2.0]

# 解なしの例（全期間同符号）
try:
    core.irr([1000, 2000, 3000])
except core.InvalidCashFlowError as e:
    print(e)
```

CSV/Excel から読み込む場合は `irr_xirr_tool.io`:

```python
from irr_xirr_tool import io as cfio

series = cfio.load_cashflows("cashflows.csv")   # or .xlsx
series.amounts   # List[float]
series.dates     # List[datetime.date] または None（IRRモード）
```

## 2. CLI として使う

```bash
# 手入力（等間隔 -> IRR）。先頭がマイナス値でもそのまま渡せます。
irr-tool --amounts "-1000000,300000,300000,300000,300000,300000" --rate 8%

# 日付付き（不等間隔 -> XIRR）
irr-tool --dated "2008-01-01:-10000,2008-03-01:2750,2008-10-30:4250,2009-02-15:3250,2009-04-01:2750"

# CSV / Excel から読み込み
irr-tool --csv cashflows.csv --rate 0.08 --finance-rate 0.08 --reinvest-rate 0.10
irr-tool --excel cashflows.xlsx --sheet 0

# JSON 出力（他ツールとの連携用）
irr-tool --amounts "-1000000,300000,300000,300000,300000,300000" --json
```

出力例:

```
Mode: IRR (equally-spaced cash flows)  |  6 cash flows

IRR: 15.2382%
  Unique real solution found.

Payback period: 3.333 periods

NPV @ 8.0000%: 197,813.01

MIRR (finance=8.0000%, reinvest=8.0000%): 11.9700%
```

複数解の場合は `IRR: MULTIPLE SOLUTIONS FOUND` として全解を列挙し、解なしの
場合は `IRR: NO REAL SOLUTION FOUND` と明示します（終了コード: 正常/複数解=0、
実数解なし=1、入力エラー=2）。

CSV/Excel フォーマット:
- 単一列 `amount`（ヘッダー省略可）→ IRR モード（行の順序 = 期0, 1, 2, ...）
- 2列 `date, amount`（ヘッダー省略可。ヘッダーが無い場合は1列目が日付として
  解釈できれば自動判定）→ XIRR モード

## 3. Web アプリとして使う

```bash
python -m irr_xirr_tool.webapp
# -> http://127.0.0.1:5000 で起動
```

ブラウザで開くと、手入力（動的な行追加/削除テーブル）・CSVアップロード・
Excelアップロードの3方式でキャッシュフローを入力でき、IRR/XIRR・NPV・回収期間・
MIRRを算出します。複数解・解なしの場合はその旨を画面上に明示します。

本番運用する場合は `flask run` の開発サーバーではなく gunicorn 等の WSGI
サーバー経由で `irr_xirr_tool.webapp:create_app` を利用してください。

## テスト

```bash
pytest -v
```

`tests/test_core.py` に Excel 公式ドキュメント例題との数値一致検証、複数解・
解なしケース、`tests/test_io.py` に CSV/Excel 入力パース、`tests/test_cli.py` /
`tests/test_webapp.py` に CLI・Web アプリの結合テストがあります。
