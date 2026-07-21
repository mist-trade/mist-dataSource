# QMT Native Datasource Notes

Reviewed on 2026-07-19 against the Theme A mode-gated realtime direction.

QMT is no longer modeled as a TDX-compatible provider inside the TDX service.
Mist should call TDX on `:9001` and QMT on `:9002` as two separate datasource
services. Cross-provider row shaping, chart unification, and backtest input
normalization belong in Mist backend or strategy code, not inside the QMT
datasource.

## Current Boundary

- TDX service `:9001` always exposes TDX `/v1` and its builtin realtime bridge;
  it has no realtime mode switch.
- QMT service `:9002` exposes `/health`, `:9002/v1/bars/query`, and the
  full-QMT HTTP polling bridge endpoints used by the built-in Python script.
- `QMT_REALTIME_MODE=builtin_experimental` additionally exposes datasource-side
  `/ws/qmt-experimental/{clientId}` and loopback `/qmt/realtime/health`.
- QMT native `marketData` is returned as column-oriented JSON shaped after
  `ContextInfo.get_market_data_ex(..., subscribe=False)`: `{field: {stime:
  value}}`.
- QMT source code lives under `src/datasource/qmt_provider.py` and
  `src/datasource/qmt/*`; no shared TDX adapter layer exists.
- Historical QMT bars map to `get_market_data_ex(..., subscribe=False)` and do
  not trigger quote subscription.
- QMT production bridge transport is stdlib HTTP polling only:
  `commands -> owner -> poll -> result -> health`.
- QMT built-in production script must not use third-party packages, threads,
  subprocesses, separate Python processes, local port listeners, or WebSocket
  transport.
- The experimental QMT WebSocket is downstream of the datasource. It does not
  change the built-in script transport or native historical response shape.

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

The production endpoint enqueues `get_market_data_ex` on the single-owner
command gateway. The full-QMT built-in script executes it with
`subscribe=False` and posts the native column-oriented result back. It does not
subscribe and does not read DAT files in the datasource process.

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
    "source": "native_bridge"
  }
}
```

`include_raw=true` adds bounded bridge evidence under `rawMeta`, including the
native method and command id. It does not expose a lease token.

No DAT reader or QMT data-directory configuration is part of this service.
Missing or stale bridge ownership returns a stable retryable bridge error.

## Bridge Commands

The bridge command gateway is intentionally narrow and stays under
`/qmt/bridge/*`; it is not part of the TDX `/v1` contract. Operators or future
QMT product code enqueue one whitelisted command through
`POST :9002/qmt/bridge/commands`, then the full-QMT built-in Python script polls
and posts the result. The initial whitelist is `health`, `get_market_data_ex`,
`get_full_tick`, and `get_stock_list_in_sector`.

## Verification Owners

- Native QMT bars are guarded by `tests/unit/test_qmt_provider.py` and
  `tests/integration/test_qmt_v1.py`.
- Full-QMT HTTP polling bridge behavior is guarded by
  `tests/unit/test_qmt_command_gateway.py` and
  `tests/integration/test_qmt_bridge_routes.py`.
- Static cleanup guardrails are guarded by
  `tests/unit/test_bigqmt_bridge_guardrails.py`.
