# Proposal: instrument-datasource-bridge-ingest

## Why

O0（OTel + OpenObserve）接通了基础：FastAPIInstrumentor 自动给 HTTP 请求建 span，
OpenObserve 能看到"POST /tdx/bridge/snapshot 返回 200/409"——但**链路内部完全不可见**。

审计确认（2026-08-09）bridge → datasource 接收段的所有判断点（TDX 8 个、QMT 8 个）
**零日志、零 span、零计数**：
- TDX：loopback / pydantic / gateway ready / captured_at / native safety / native decode /
  owner-epoch / symbol 收敛集门禁
- QMT：loopback / owner / captured_at / subscription_id / per-symbol accept-reject 循环 / publish gate
- 两个**静默丢弃点**：TDX symbol 不在收敛集（无任何痕迹）、WS per-client send 失败 eviction

2026-08-07 TDX 断流 56 分钟零告警的教训：当时只知道 backend sealed 停滞，无法判断
"datasource 没收到"还是"backend 没处理"。本 change 补齐**数据链路前半段**（bridge →
datasource）的可观测性：日志（人类可读细节）+ span（结构化追踪）+ 指标（健康度告警）。

同时**直接覆盖 C1 启动异常**（QMT `context-rebuild-observation.json` + `.processing` 并存
→ 启动抛错）：不再只靠进程退出后 bridge_ready 消失间接判断，而是启动路径直接埋点。

## What Changes

### 1. TDX snapshot 接收链路埋点（tdx/routes/bridge.py + tdx/realtime/gateway.py）

每个 snapshot 处理一个根 span `tdx.snapshot.ingest`，链路 3 个生命周期日志点 + 判断点埋点：
- 日志：进入（symbol/capturedAt/bytes）→ 转换完成（frame_schema=2）→ broadcast（clients）
- 判断点拒绝：span event（reason）+ warn 日志 + rejected 计数

### 2. QMT snapshot 接收链路埋点（qmt/routes/bridge.py + qmt/realtime/subscription.py）

对称结构，根 span `qmt.snapshot.ingest`，per-symbol accept/reject 循环每个拒绝分支埋点。

### 3. WS broadcast 埋点（ws/manager.py）

- span 子节点 `ws.broadcast`（clients 数、耗时、send 失败数）
- **per-client send 失败不再是静默**：warn 日志 + span event + eviction 可见

### 4. QMT 启动失败直接覆盖（qmt/main.py + src/core/otel.py）

- **OTel provider 初始化提前**：`setup_logging()` 后即初始化（不再等 app 创建），
  启动 span `qmt.startup` 覆盖 `create_qmt_app()` 全程
- `consume_rebuilt_context_observation` 检查点：成功/失败都打结构化日志
- 失败路径：span `set_status(ERROR)` + record_exception + 尝试 flush（进程 crash 前）
- 成功路径：`mist_datasource_startup_ok{source}=1` gauge（进程退出后序列消失可检测）

### 5. datasource 链路健康度指标（OTel metrics API）

| 指标 | 类型 | 来源 |
|---|---|---|
| `mist_datasource_snapshot_age_seconds{source}` | gauge | gateway `_last_snapshot_monotonic` |
| `mist_datasource_snapshot_accepted_total{source}` | counter | **新增**计数（当前不存在） |
| `mist_datasource_snapshot_rejected_total{source,reason}` | counter | **新增**计数（按判断点 reason） |
| `mist_datasource_bridge_ready{source}` | gauge | bridge.ready |
| `mist_datasource_owner_stale{source}` | gauge | owner stale 状态 |
| `mist_datasource_control_total{source,operation,result,reason}` | counter | 现有 `_control_counts` |
| `mist_datasource_ws_clients{source}` | gauge | ConnectionManager.connection_count |
| `mist_datasource_startup_ok{source}` | gauge | 启动成功置 1（进程退出消失） |

新增计数 2 个（accepted/rejected），其余 6 个从现有状态读。

## Scope

### In scope
- mist-datasource 仓：埋点 + 指标 + 启动覆盖 + 单测
- mock 环境适配（验证闭环：注入 → OpenObserve 可见 span/指标 → 停注入 → age 增长）

### Out of scope
- **backend 侧判断点**（ingress → aggregator → finalizer 的 skip/discard）→ O1 单独 change
- QMT 17 个 `mist_qmt_*` 细节指标（无告警引用，按需再加）
- WS trace context 跨进程传播（datasource → backend 的 WS 推送串联）→ 后续 change
- OTLP logs 接入 OpenObserve（日志继续走 stdout）
