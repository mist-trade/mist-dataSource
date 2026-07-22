# TdxQuant Live Datasource Smoke Reference

Captured from the official TdxQuant documentation on 2026-06-27.

Coverage matrix:
`docs/references/tdxquant-interface-coverage.md`.

Related broader page capture:
`docs/references/tdxquant-official-page-capture-2026-06-27.md`.

This file records only the TDX APIs needed to design and maintain a fast
Windows live smoke test for `mist-datasource`. It is intentionally scoped to the
datasource gateway path:

- native TdxQuant HTTP JSON-RPC at `http://127.0.0.1:17709/`
- TDX `/v1` normalized HTTP routes exposed by this repository
- TDX WebSocket subscription flow used by NestJS

## Source Pages

- TdxQuant overview: <https://help.tdx.com.cn/quant/>
- HTTP call mode: <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hdhbmi50d038.html>
- K-line data `get_market_data`: <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10g60jt68sc.html>
- Snapshot data `get_market_snapshot`: <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10iig4pb6e0.html>
- Initialize `initialize`: <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1cv85e8u9nb0c.html>
- Subscribe `subscribe_hq`: <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h1104d65vr68.html>
- Unsubscribe `unsubscribe_hq`: <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h112vh7jtsms.html>
- Sector list `get_sector_list`: <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r5907noko.html>
- Sector members `get_stock_list_in_sector`: <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r92mchgug.html>

## Environment Requirements

The official docs state that each strategy must initialize TdxQuant with:

```python
from tqcenter import tq
tq.initialize(__file__)
```

The TDX terminal that supports TQ strategies must already be running and logged
in before live datasource tests run.

For this repository, datasource does not read `TDX_SDK_PATH` or load
`TPythClient.dll`. The operator installs `tqcenter.py` and the builtin bridge in
the TDX terminal's `PYPlugins/user` environment; the WinSW datasource process
uses only HTTP and WebSocket boundaries.

## Native HTTP JSON-RPC

The TdxQuant HTTP gateway accepts POST requests at:

```text
http://127.0.0.1:17709/
```

Request shape:

```json
{
  "id": 1,
  "method": "get_market_data",
  "params": {
    "stock_list": ["688318.SH"],
    "count": 5,
    "dividend_type": "none",
    "period": "1d"
  }
}
```

`method` is a TdxQuant function name and `params` are that function's
parameters.

## `get_market_data`

Signature from docs:

```python
get_market_data(
    field_list: list[str] = [],
    stock_list: list[str] = [],
    period: str = "",
    start_time: str = "",
    end_time: str = "",
    count: int = -1,
    dividend_type: str | None = None,
    fill_data: bool = True,
) -> dict
```

Important parameters:

| Parameter | Required | Notes |
| --- | --- | --- |
| `stock_list` | yes | TDX symbols such as `688318.SH` |
| `period` | yes | e.g. `1d`, `1m` |
| `field_list` | no | empty means return all fields |
| `start_time` | no | TDX date string |
| `end_time` | no | TDX date string |
| `count` | no | rows per stock |
| `dividend_type` | no | `none`, `front`, `back` |
| `fill_data` | no | whether to forward-fill missing data |

Official docs note that one call can return at most 24,000 records. Complete
minute history needs batching.

### Native Python Return Shape

The Python SDK form returns:

```text
{
  field1: pandas.DataFrame,
  field2: pandas.DataFrame,
  ...
}
```

Each field DataFrame uses `stock_list` as index and the time list as columns.

Default fields include:

- `Date`
- `Time`
- `Open`
- `High`
- `Low`
- `Close`
- `Volume`
- `Amount`
- `ForwardFactor`
- `VolInStock`

### Native HTTP Return Shape

The HTTP JSON-RPC sample returns a JSON object under `result`:

```json
{
  "id": 1,
  "result": {
    "ErrorId": "0",
    "KlinePaged": true,
    "KlineTotal": {
      "688318.SH": 5
    },
    "Value": {
      "688318.SH": {
        "Amount": ["61995.09"],
        "Close": ["122.45"],
        "Date": ["20260526"],
        "ForwardFactor": ["0.711862"],
        "High": ["124.58"],
        "Low": ["117.70"],
        "Open": ["119.71"],
        "Time": ["0"],
        "VolInStock": ["0"],
        "Volume": ["5086297.00"]
      }
    },
    "has_more": false,
    "stock_total": 1
  }
}
```

Smoke tests should explicitly validate this HTTP shape before validating
normalized `/v1/bars/query`, because it differs from the Python SDK DataFrame
shape.

## `get_market_snapshot`

Signature from docs:

```python
get_market_snapshot(stock_code: str, field_list: list = []) -> dict
```

Important fields in the documented return:

- `ItemNum`
- `LastClose`
- `Open`
- `Max`
- `Min`
- `Now`
- `Volume`
- `NowVol`
- `Amount`
- `Inside`
- `Outside`
- `Buyp`
- `Buyv`
- `Sellp`
- `Sellv`
- `Average`
- `ErrorId`

The datasource normalized snapshot should map at least:

| Native field | Normalized field |
| --- | --- |
| `Now` | `last` |
| `Open` | `open` |
| `Max` | `high` |
| `Min` | `low` |
| `LastClose` | `lastClose` |
| `Volume` | `volume` |
| `Amount` | `amount` |

## `subscribe_hq`

Signature from docs:

```python
subscribe_hq(stock_list: list[str] = [], callback=None)
```

Constraints:

- `stock_list` is required.
- `callback` is required.
- Up to 100 symbols can be subscribed.
- Callback input format:

```json
{
  "Code": "XXXXXX.XX",
  "ErrorId": "0"
}
```

Official sample response:

```json
{
  "Error": "订阅688318.SH更新成功.",
  "ErrorId": "0",
  "run_id": "1"
}
```

Repository design rule: keep the callback thin. It should parse the updated
symbol, mark it dirty, and return quickly. The collector must fetch
`get_market_snapshot` and broadcast a `quote` event; `get_market_data` remains a
historical bar API and is not used as subscription fallback.

## `unsubscribe_hq`

Signature from docs:

```python
unsubscribe_hq(stock_list: list[str] = [])
```

Callback payload notes in the docs mirror `subscribe_hq`. The smoke test should
exercise unsubscribe after subscription sync so repeated manual runs do not
leave stale subscription state.

## Sector APIs

`get_sector_list` signature:

```python
get_sector_list(list_type: int = 0) -> list
```

`list_type = 0` returns codes only. `list_type = 1` returns code and name.

`get_stock_list_in_sector` signature:

```python
get_stock_list_in_sector(
    block_code: str,
    block_type: int = 0,
    list_type: int = 0,
) -> list
```

Notes from docs:

- `block_code` can be a sector code or sector name for A-share sectors.
- `block_type = 0` means sector index code/name.
- `block_type = 1` means user-defined sector short name.
- `ZXG` means watchlist and `TJG` means temporary condition list.
- `list_type = 0` returns codes only.
- `list_type = 1` returns code and name.
- `get_stock_list_in_sector` only supports custom sectors or 15 sector-index
  sectors; it does not support broad system groups like all A shares or
  Shanghai/Shenzhen A shares.

## Recommended Smoke Test Contract

### Basic Mode

Basic mode should run outside trading hours and validate the fastest real TDX
gateway path:

1. `GET /health`
   - service responds
   - `tdxHttpReachable` is true
   - `tqInitialized` is true when exposed
2. `POST /v1/raw/tdx/call` with `method=get_market_data`
   - native result has `Open`, `High`, `Low`, `Close`, `Volume`, `Amount`
     through one of the fixture-backed shapes: direct field tables,
     `Value[symbol]`, or top-level `symbol`
3. `POST /v1/bars/query`
   - envelope `ok=true`
   - `data.bars` is non-empty
   - normalized bars contain numeric OHLCV fields
4. `POST /v1/raw/tdx/call` with `method=get_market_snapshot`
   - native result has `Now`, `LastClose`, `Open`, `Max`, `Min`, `Volume`,
     `Amount`, and `ErrorId`
5. `POST /v1/snapshots/query`
   - envelope `ok=true`
   - normalized snapshots contain `last`, `open`, `high`, `low`, `lastClose`,
     `volume`, `amount`, and `asOf`
6. `POST /v1/raw/tdx/call` with `method=get_stock_list_in_sector`
   - result is a non-empty list for a known sector such as `880081.SH`
7. `POST /v1/sectors/query`
   - normalized symbols are returned

### Finance/Report Optional Mode

Run this after basic mode when validating Phase 3 datasource coverage:

```powershell
.\scripts\run-runtime-checks.ps1 `
  -ApplianceRoot F:\quant\MistAPI `
  -IncludeFinanceReportSmoke
```

The optional probe uses read-only finance/report calls that are present in the
current official TDX finance navigation:

1. `POST /v1/raw/tdx/call` with `method=get_gp_one_data`
   - native result contains the requested field for the requested symbol
2. Normalized finance endpoints:
   - `/v1/finance/financial-data/query`
   - `/v1/finance/financial-data/by-date/query`
   - `/v1/finance/single-data/query`
3. Normalized trade aggregate endpoints:
   - `/v1/reports/stock-trade/query`
   - `/v1/reports/stock-trade/by-date/query`
   - `/v1/reports/sector-trade/query`
   - `/v1/reports/sector-trade/by-date/query`
   - `/v1/reports/market-trade/query`
   - `/v1/reports/market-trade/by-date/query`

`/v1/reports/data/query` is not exposed because the current official finance
navigation does not list `get_report_data`, and the validated TDX MCP runtime
returns `-32601` for that tqcenter method.

### Reference/Instrument Optional Mode

Run this when validating Phase 2 reference/instrument coverage:

```powershell
.\scripts\run-runtime-checks.ps1 `
  -ApplianceRoot F:\quant\MistAPI `
  -IncludeReferenceInstrumentSmoke
```

The optional probe uses `get_gb_info` plus
`/v1/reference/share-capital/query` for a stable read-only check.

### Formula Optional Mode

Run this when validating Phase 4 formula coverage:

```powershell
.\scripts\run-runtime-checks.ps1 `
  -ApplianceRoot F:\quant\MistAPI `
  -IncludeFormulaSmoke
```

The optional probe uses read-only formula metadata:

1. `POST /v1/raw/tdx/call` with `method=formula_get_all`
2. `POST /v1/formulas/metadata/query`

Formula execution endpoints are normalized but intentionally guarded by request
size and timeout limits; run execution tests separately with operator-selected
formulas.

### Fixture-backed HTTP Shapes

`tests/unit/test_tdx_provider.py` keeps regression fixtures for documented TDX
HTTP `Value` wrappers and Windows-smoke-compatible runtime variants. The basic
bar fixtures cover direct field tables, `Value[symbol]` array rows, and
top-level `symbol` array rows, so changes in TDX bridge wrapping fail locally
before appliance smoke testing.

### Live Subscription Mode

Live mode is trading-time sensitive:

1. Ensure the backend leader is connected to
   `ws://127.0.0.1:9001/ws/tdx-experimental/<client_id>`.
2. Expect a `ready` message.
3. The backend leader sends the complete desired set:

```json
{
  "type": "sync_subscriptions",
    "symbols": ["688318.SH"]
}
```

4. Expect desired/converged revisions to match.
5. Optionally wait for a typed `tdx.realtime.snapshot` frame.
6. Remove the test symbol through the backend leader and resync the complete
   desired set before exit.

The snapshot wait should be optional by default and mandatory only when the
runner passes a flag such as `--require-live-quote`, because live callback
timing depends on market hours and TDX terminal state.

## Current Verification Owner

The maintained Windows wrapper lives in `mist-deploy`:

```text
scripts/run-tdx-runtime-smoke.ps1
Run Windows TDX Runtime Smoke
```

It derives the builtin WebSocket path, verifies bridge readiness and official
HTTP reachability, and keeps subscription mutation backend-owned.
