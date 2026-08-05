# TDX Datasource 依赖链路

TDX 有两条互相独立的生产链路。`TDX_REALTIME_MODE=builtin|off` 只控制 realtime
gateway 与 route；HTTP provider 始终保留。

## 非实时 HTTP provider

```text
/v1/* -> TdxDatasourceProvider -> TdxHttpClient -> 127.0.0.1:17709
```

该链路负责历史 bars、reference、finance、sector、report、formula 和 operator
raw calls。它不 import `tqcenter`，也不订阅实时行情。

## Builtin realtime bridge

```text
TDX terminal strategy (builtin script)
  -> /tdx/bridge/*
  -> typed realtime gateway
  -> /ws/realtime/tdx/{client_id}
  -> Mist backend leader
```

终端脚本是唯一 native SDK owner，使用 `subscribe_hq` 和官方
`get_market_snapshot`，每 3 秒（`POLL_INTERVAL_SECONDS`）通过 loopback HTTP 获取
完整 desired subscription set，并回传 native snapshot。Datasource 在 HTTP 边界验证
一次，再广播稳定 frame；backend 在 WebSocket 边界验证一次，不重复重建 native
object。

## 已删除边界

- datasource 进程内 `tqcenter` adapter
- dirty collector 与旧 subscription client
- `/api/tdx/*`
- `/v1/snapshots/query` 与 datasource/provider 的按需 snapshot wrapper
- `/ws/quote/{client_id}`
- 旧 experimental realtime route 与 mode 名称

产品 HTTP 调用使用 `/v1/*`，实时 consumer 使用 builtin realtime WebSocket。当前
datasource 实现位于 `src/datasource/tdx/provider.py` 与
`src/datasource/tdx/realtime/{gateway.py,contract.py}`。
