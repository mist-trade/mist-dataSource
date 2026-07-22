# TDX Datasource 依赖链路

TDX 有两条互相独立的生产链路，no runtime mode switch。

## 非实时 HTTP provider

```text
/v1/* -> TdxDatasourceProvider -> TdxHttpClient -> 127.0.0.1:17709
```

该链路负责历史 bars、HTTP snapshot、reference、finance、sector、report、formula
和 operator raw calls。它不 import `tqcenter`，也不订阅实时行情。

## Builtin realtime bridge

```text
TDX terminal strategy (builtin script)
  -> /tdx/bridge/*
  -> typed realtime gateway
  -> /ws/tdx-experimental/{client_id}
  -> Mist backend leader
```

终端脚本是唯一 native SDK owner，使用 `subscribe_hq` 和官方
`get_market_snapshot`，每秒通过 loopback HTTP 获取完整 desired subscription set，
并回传 native snapshot。Datasource 在 HTTP 边界验证一次，再广播稳定 frame；backend
在 WebSocket 边界验证一次，不重复重建 native object。

## 已删除边界

- datasource 进程内 `tqcenter` adapter
- dirty collector 与旧 subscription client
- `/api/tdx/*`
- `/ws/quote/{client_id}`
- `TDX_REALTIME_MODE`

产品 HTTP 调用使用 `/v1/*`，实时 consumer 使用 builtin realtime WebSocket。
