# TDX datasource dependency flow

TDX has two independent production paths and no runtime mode switch.

## HTTP provider

`/v1/* -> TdxDatasourceProvider -> TdxHttpClient -> 127.0.0.1:17709`

This path owns historical bars, snapshots requested over HTTP, reference,
finance, sector, formula, and raw operator calls. It does not import `tqcenter`
or subscribe to realtime quotes.

## Builtin realtime bridge

`TDX terminal strategy -> /tdx/bridge/* -> realtime gateway -> /ws/tdx-experimental/{client_id} -> Mist backend`

The manually registered terminal script is the single native SDK owner. It
uses `subscribe_hq` and `get_market_snapshot`, polls desired state over loopback
HTTP, and posts native snapshots back to datasource. Datasource validates each
snapshot once and broadcasts the typed frame.

TDX realtime is always mounted. QMT retains its own independent
`QMT_REALTIME_MODE` switch.

## Removed surfaces

The datasource no longer contains the process-local adapter, dirty collector,
legacy `/api/tdx/*` routes, or `/ws/quote/{client_id}`. Product callers use
`/v1/*`; realtime consumers use the builtin bridge WebSocket.
