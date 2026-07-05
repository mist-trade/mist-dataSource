# QMT Native Datasource Notes

Reviewed on 2026-07-05 against the full-QMT built-in Python direction.

QMT is no longer modeled as a TDX-compatible provider inside the TDX service.
Mist should call TDX on `:9001` and QMT on `:9002` as two separate datasource
services. Cross-provider row shaping, chart unification, and backtest input
normalization belong in Mist backend or strategy code, not inside the QMT
datasource.

## Current Boundary

- TDX service `:9001` exposes TDX `/v1` contracts and TDX WebSocket quote
  streaming only.
- QMT service `:9002` exposes `/health`, `:9002/v1/bars/query`, and the
  full-QMT HTTP polling bridge endpoints used by the built-in Python script.
- QMT native `marketData` is returned as column-oriented JSON shaped after
  `ContextInfo.get_market_data_ex(..., subscribe=False)`: `{field: {stime:
  value}}`.
- QMT does not implement `src.adapter_legacy.base.TdxLegacyAdapterBase`. That adapter
  package is now TDX-only legacy glue; QMT source code lives under
  `src/datasource/qmt_provider.py` and `src/datasource/qmt/*`.
- Historical QMT bars map to `get_market_data_ex(..., subscribe=False)` and do
  not trigger quote subscription.
- QMT production bridge transport is stdlib HTTP polling only:
  `commands -> owner -> poll -> result -> health`.
- QMT built-in production script must not use third-party packages, threads,
  subprocesses, separate Python processes, local port listeners, or WebSocket
  transport.

## Native Bars

`POST :9002/v1/bars/query` accepts QMT-style snake_case request parameters:

```json
{
  "fields": [],
  "stock_list": ["000001.SZ"],
  "period": "1d",
  "start_time": "",
  "end_time": "",
  "count": -1,
  "dividend_type": "none",
  "fill_data": true,
  "include_raw": false
}
```

The first implementation reads configured full-QMT local DAT files for `1d`,
`1m`, and `5m`. It is historical-only and does not subscribe. Daily volume is
kept in the DAT native unit; it is not converted to TDX share volume.

Example response shape:

```json
{
  "ok": true,
  "provider": "qmt",
  "data": {
    "marketData": {
      "000001.SZ": {
        "open": {"20260701": 10.05},
        "close": {"20260701": 10.16},
        "volume": {"20260701": 906890.0},
        "amount": {"20260701": 915838549.0}
      }
    },
    "source": "local_dat"
  }
}
```

`include_raw=true` adds DAT parse evidence under `rawMeta`, including
`period_code`, `record_size`, `header_size`, `struct_format`, `price_scale`,
and `source_path`.

## Bridge Commands

The bridge command gateway is intentionally narrow and stays under
`/qmt/bridge/*`; it is not part of the TDX `/v1` contract. Operators or future
QMT product code enqueue one whitelisted command through
`POST :9002/qmt/bridge/commands`, then the full-QMT built-in Python script polls
and posts the result. The initial whitelist is `health`, `get_market_data_ex`,
`get_full_tick`, and `get_stock_list_in_sector`.

## Verification Owners

- Native QMT bars are guarded by `tests/unit/test_qmt_local_dat_reader.py`,
  `tests/unit/test_qmt_provider.py`, and `tests/integration/test_qmt_v1.py`.
- Full-QMT HTTP polling bridge behavior is guarded by
  `tests/unit/test_qmt_command_gateway.py` and
  `tests/integration/test_qmt_bridge_routes.py`.
- Static cleanup guardrails are guarded by
  `tests/unit/test_bigqmt_bridge_guardrails.py`.
