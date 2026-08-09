# Design: instrument-datasource-bridge-ingest

## 决策

### D1. span 粒度：根 span + 判断点 event（不建深树）

每个 snapshot 一个根 span，**不为每个判断点建独立 span**（避免每帧 8-10 层深树噪音）。

```
tdx.snapshot.ingest                    ← 根 span（覆盖整个处理链）
  ├── span event: rejected{reason}     ← 任一判断点拒绝时（set_status(ERROR)）
  └── ws.broadcast                     ← 子 span（clients/耗时/send 失败数）
```

成功路径 2 层，拒绝路径根 span 标 ERROR + event 带 reason。
理由：判断点的**存在性**（拒绝发生）用 event 表达足够，深度排查靠日志细节 + 指标聚合。

### D2. 日志：3 个生命周期点 + 拒绝 warn

```
[info]  ingest start   source=tdx symbol=600519.SH capturedAt=... payload_bytes=1234
[info]  frame built    source=tdx frame_schema=2 accepted=True
[info]  broadcast      source=tdx clients=3 frame_bytes=512
[warn]  ingest reject  source=tdx reason=TDX_BRIDGE_SYMBOL_NOT_CONVERGED symbol=...
[warn]  send failed    source=tdx client=xxx error=... (evicted)
```

结构化（key=value 或 JSON），走 Python logging → stdout（Docker 收集，O0 决策不改）。
**日志注入 trace_id**：Python logging 里读 `trace.get_current_span()` 的 context，
把 trace_id 拼进日志行——OpenObserve 里从 trace 下钻日志，或从日志反查 trace。

### D3. 指标：OTel metrics API，8 个

新增 2 个 counter（accepted/rejected），6 个 gauge 从现有状态读。reason 枚举：
- TDX rejected reason：`not_loopback | not_ready | invalid_timestamp | native_unsafe |
  native_invalid | owner_not_locked | lease_invalid | epoch_mismatch | symbol_not_converged`
- QMT rejected reason：`not_loopback | ownership_invalid | captured_at_invalid |
  subscription_id_invalid | symbol_invalid | non_member | native_invalid | native_unsafe`
- `snapshot_rejected_total{source,reason}` 的 reason 是上述有界枚举（低基数）

### D4. OTel provider 初始化提前（C1 直接覆盖的关键）

现状：`configure_otel(app, name)` 在 `app = create_*_app()` 之后调用——
QMT 启动抛错时 OTel 尚未初始化，span 发不出去。

重构 `src/core/otel.py` 为两个函数：
```python
def init_otel(service_name: str) -> None:
    """模块顶层调用（setup_logging 后、app 创建前）。
    只初始化 TracerProvider + MeterProvider + exporters，不 instrument app。
    no-op guard + 幂等保持。"""

def instrument_app(app: FastAPI) -> None:
    """app 创建后调用。FastAPIInstrumentor.instrument_app(app)。"""
```

调用点变化：
- `tdx/main.py`：`setup_logging()` 后 `init_otel("tdx-datasource")`，`app = create_tdx_app()`
  后 `instrument_app(app)`
- `qmt/main.py`：同上——**启动失败（create_qmt_app 抛错）时 span 已能发出**

### D5. 启动 span（C1）

```
qmt.startup  ← 在 create_qmt_app() 调用前开始，覆盖启动全程
  ├── 成功：status OK + mist_datasource_startup_ok{qmt}=1
  └── 失败（consume_rebuilt_context_observation 抛错）：
      status ERROR + record_exception + 同步 force_flush + error 日志 + raise
```

**关键：失败路径必须用 `provider.force_flush()`（同步导出）**，不能用
BatchSpanProcessor 的默认异步导出——进程 crash 时异步队列里的 span 会丢失。
`create_qmt_app()` 用 try/except 包裹，except 里依次：error 日志（stdout 必达）→
span 标 ERROR → force_flush（等 HTTP 完成）→ 重新 raise（异常传播 → 进程退出）。

**三重覆盖**：
1. error 日志（stdout，Docker 收集——最可靠）
2. ERROR span + force_flush（OpenObserve 可达则必达——直接看到失败 trace）
3. `startup_ok` 序列消失（成功启动才有 =1，失败进程退出无此序列——可查询佐证）

`consume_rebuilt_context_observation` 检查点（qmt/main.py:108）：
- 检查前：`[info] qmt startup: consuming context-rebuild observation path=...`
- 失败：`[error] qmt startup failed: ambiguous context rebuild observation state
  path=... processing_marker=...`（带具体文件）

### D6. WS broadcast 埋点（静默丢弃点修复）

`ConnectionManager.broadcast`：
- 子 span `ws.broadcast`（clients 数、耗时、send_failed 数）
- per-client send 失败：`[warn] send failed source=... client=... error=...` + eviction
  （当前完全静默，只从 connection_count 间接看）

### D7. mock 验证闭环

```
run-mock.sh 起栈（openobserve + datasource + backend，OTel env 指向 mock openobserve）
  → mock-drive.py --source tdx 注入
  → OpenObserve 查询：tdx.snapshot.ingest span 存在 + snapshot_accepted 增长 + age 正常
  → 停止注入（A2 断流）
  → OpenObserve 查询：age 增长 + ingest span 消失 + accepted 停止
  → C1：构造 context-rebuild-observation.json + .processing → qmt 启动
    → 日志有 error + OpenObserve 有 qmt.startup ERROR span（尽力）
```

mock 环境的 datasource 启动命令需要带 `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:5080`
（run-mock.sh 的 openobserve 容器端口 5080）。

## 影响链

```
mist-datasource 仓
  ├── src/core/otel.py          # 拆 init_otel / instrument_app
  ├── tdx/main.py               # init_otel 提前 + instrument_app
  ├── qmt/main.py               # 同上 + 启动 span + observation 检查点日志
  ├── tdx/routes/bridge.py      # snapshot 路由埋点
  ├── tdx/realtime/gateway.py   # 判断点埋点 + accepted/rejected 计数
  ├── qmt/routes/bridge.py      # 对称
  ├── qmt/realtime/subscription.py  # per-symbol 循环埋点 + 计数
  ├── qmt/realtime/runtime.py   # startup_ok 指标
  ├── ws/manager.py             # broadcast 埋点
  ├── src/datasource/metrics.py # （新建）OTel 指标定义（8 个）
  ├── src/core/logging.py       # trace_id 注入
  └── tests/                    # 单测（span 断言 + 指标断言 + 日志断言）
```

## 边界

- 不改任何判断点的**行为**（拒绝逻辑、错误码、返回结构全不变），只加观测
- `controlTotals` 保持只计 control-plane（不动现有语义）；snapshot 计数用新指标
- 指标低基数：reason 有界枚举，不携带 symbol/ownerId/lease token
- WS 帧的 trace context 跨进程传播**不在本 change**（datasource push → backend 的
  串联是 WS 协议层，后续单独 change）
