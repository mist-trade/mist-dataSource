# O2a 实施计划：instrument-datasource-bridge-ingest

> 代码级实施计划（三步流程第二步）。spec 已确认，本计划细化到文件/函数/测试/验证命令。
> 实施计划确认通过后才落地。

---

## 1. src/core/otel.py：拆 init_otel / instrument_app

**现状**：`configure_otel(app, service_name)` 一个函数（provider + instrument_app 一起）。
**改后**：

```python
_configured = False  # provider 层标志

def init_otel(service_name: str) -> None:
    """模块顶层调用（setup_logging 后、app 创建前）。
    只初始化 TracerProvider + MeterProvider + exporters。
    no-op guard（OTEL_EXPORTER_OTLP_ENDPOINT 未配置跳过）+ 幂等。
    导出 provider 引用供启动失败路径 force_flush。"""
    global _configured, _tracer_provider, _meter_provider
    if _configured:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return
    resource = Resource.create({"service.name": service_name})
    _tracer_provider = TracerProvider(resource=resource)
    _tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_tracer_provider)
    _meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(_meter_provider)
    _configured = True

def instrument_app(app: FastAPI) -> None:
    """app 创建后调用。FastAPIInstrumentor.instrument_app(app)。"""
    FastAPIInstrumentor.instrument_app(app)

def force_flush() -> None:
    """启动失败路径：同步导出（等 HTTP 完成），进程 crash 前调用。"""
    if _tracer_provider is not None:
        _tracer_provider.force_flush()

def shutdown_otel() -> None:
    global _configured
    _configured = False
```

模块级 `_tracer_provider` / `_meter_provider` 初始为 None。

## 2. src/core/logging.py：trace_id 注入

**现状**：`logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")`
**改后**：自定义 Formatter 子类：

```python
class TraceContextFormatter(logging.Formatter):
    def format(self, record):
        span = trace.get_current_span()
        ctx = trace.get_current_span().get_span_context() if span else None
        if ctx is not None and ctx.is_valid:
            record.trace_id = f"{ctx.trace_id:032x}"[:16]
            record.span_id = f"{ctx.span_id:016x}"
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return super().format(record)
```

format 改为：
`"%(asctime)s - %(name)s - %(levelname)s - trace=%(trace_id)s span=%(span_id)s - %(message)s"`

`setup_logging()` 里 `logging.basicConfig(..., formatter=TraceContextFormatter(...))`
（注意 basicConfig 需要先 clearHandlers 或用 handlers 参数——当前用 StreamHandler，改
`handlers=[logging.StreamHandler(sys.stdout)]` 且给 handler 设 formatter）。

## 3. src/datasource/metrics.py（新建）

```python
"""Datasource 链路健康度指标（OTel metrics API，低基数）。"""
from opentelemetry import metrics

def _meter() -> metrics.Meter:
    # 惰性获取：模块级缓存 _ProxyMeter 虽会委托（已验证），惰性更清晰
    return metrics.get_meter("mist-datasource", "0.1.0")

# 仪器注册一次（同名重复 create 会抛 DuplicateMetricError）
_INSTRUMENTS: dict[str, object] = {}

def init_metrics() -> None:
    """init_otel() 之后调用一次（幂等）。"""
    if _INSTRUMENTS:
        return
    m = _meter()
    _INSTRUMENTS["accepted"] = m.create_counter(
        "mist_datasource_snapshot_accepted_total",
        description="Accepted bridge snapshots per source",
    )
    _INSTRUMENTS["rejected"] = m.create_counter(
        "mist_datasource_snapshot_rejected_total",
        description="Rejected bridge snapshots per source and reason",
    )
    _INSTRUMENTS["bridge_ready"] = m.create_gauge(
        "mist_datasource_bridge_ready",
        description="Bridge readiness per source (1 ready / 0 not)",
    )
    _INSTRUMENTS["owner_stale"] = m.create_gauge(
        "mist_datasource_owner_stale",
        description="Owner staleness per source (1 stale / 0 fresh)",
    )
    _INSTRUMENTS["control"] = m.create_counter(
        "mist_datasource_control_total",
        description="Subscription control outcomes",
    )
    _INSTRUMENTS["ws_clients"] = m.create_gauge(
        "mist_datasource_ws_clients",
        description="Connected WebSocket clients per source",
    )
    _INSTRUMENTS["startup_ok"] = m.create_gauge(
        "mist_datasource_startup_ok",
        description="Successful startup per source (1 ok; absent after crash)",
    )

def register_snapshot_age_callback(source: str, callback) -> None:
    """main.py 在 gateway 实例可用后调用（幂等）：
    callback(observer) -> observer.observe(gateway.snapshot_age_seconds(), {"source": source})"""
    if "age" in _INSTRUMENTS:
        return
    _INSTRUMENTS["age"] = _meter().create_observable_gauge(
        "mist_datasource_snapshot_age_seconds",
        description="Seconds since last accepted snapshot per source",
        callbacks=[callback],
    )

# 辅助函数（只引用已注册仪器）
def record_snapshot_accepted(source: str) -> None:
    _INSTRUMENTS["accepted"].add(1, {"source": source})

def record_snapshot_rejected(source: str, reason: str) -> None:
    _INSTRUMENTS["rejected"].add(1, {"source": source, "reason": reason})

def set_bridge_ready(source: str, ok: bool) -> None:
    _INSTRUMENTS["bridge_ready"].set(1 if ok else 0, {"source": source})

def set_owner_stale(source: str, stale: bool) -> None:
    _INSTRUMENTS["owner_stale"].set(1 if stale else 0, {"source": source})

def record_control(source: str, operation: str, result: str, reason: str) -> None:
    _INSTRUMENTS["control"].add(1, {"source": source, "operation": operation, "result": result, "reason": reason})

def set_ws_clients(source: str, count: int) -> None:
    _INSTRUMENTS["ws_clients"].set(count, {"source": source})

def set_startup_ok(source: str, ok: bool) -> None:
    _INSTRUMENTS["startup_ok"].set(1 if ok else 0, {"source": source})
```

**注意**：
- OTel Python 1.44 有原生 `create_gauge`（已验证）
- **仪器注册必须一次**（同名重复 create 抛 DuplicateMetricError）——`init_metrics()` 在
  `init_otel()` 后调用一次，幂等
- `_ProxyMeter` 委托已验证安全（provider 后设也 OK），但惰性 `_meter()` 更清晰
- age 用 `create_observable_gauge`（收集时实时算，回调在 main.py 注册）
- `main.py` 在 `init_otel()` 后调 `init_metrics()`

## 4. tdx/main.py + qmt/main.py：init_otel 提前 + instrument_app

**tdx/main.py**：
```python
setup_logging()
init_otel("tdx-datasource")          # 提前到 app 创建前
...
app = create_tdx_app()
instrument_app(app)                  # 替代原 configure_otel(app, "tdx-datasource")
```

**qmt/main.py**（C1 关键）：
```python
setup_logging()
init_otel("qmt-datasource")

# 启动 span + try/except 包裹
def _build_app_with_startup_trace() -> FastAPI:
    tracer = trace.get_tracer("mist-datasource")
    with tracer.start_as_current_span("qmt.startup") as span:
        try:
            app = create_qmt_app()
            span.set_status(trace.StatusCode.OK)
            metrics.set_startup_ok("qmt", 1)
            return app
        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            # error 日志（stdout 必达）——带 observation 路径 + processing marker
            log.error("qmt startup failed: %s", exc, extra={"path": ...})
            force_flush()   # 同步导出（进程 crash 前）
            raise

app = _build_app_with_startup_trace()
instrument_app(app)
```

`consume_rebuilt_context_observation` 检查点日志在 create_qmt_app 内部（qmt/main.py:108）：
```python
log.info("qmt startup: consuming context-rebuild observation path=%s", observation_path)
# 失败时（ambigous state 抛错前）：
log.error("qmt startup failed: ambiguous context rebuild observation state path=%s processing_marker=%s", ...)
```
（在 `QmtSubscriptionController.consume_rebuilt_context_observation` 里加日志，或
qmt/main.py:108 调用处 try/except。）

## 5. TDX 链路埋点

### 5.1 tdx/routes/bridge.py post_snapshot（L176-202）

路由层已有 FastAPIInstrumentor 的 HTTP span——**不再建路由 span**，只在拒绝点补日志：
```python
_require_loopback(request)          # 失败时 403——路由层已记 HTTP span，补:
                                    # log.warn("ingest reject source=tdx reason=not_loopback")
gateway = _get_gateway(request)     # 失败 409 not_ready → 同
# except GatewayError: → metrics.record_snapshot_rejected("tdx", exc.code)
# except Exception:    → metrics.record_snapshot_rejected("tdx", "decode_error")
```
**拒绝计数（修正：避免双倍）**：gateway 内部判断点的拒绝已由 gateway 层计数
（见 5.2），路由层的 `except GatewayError` 只转换 HTTP 状态码、**不重复计数**。
路由层只对自身判断点（loopback 403 / not_ready 409）在 gateway 调用**之前**计数：
```python
# _require_loopback 抛错路径
metrics.record_snapshot_rejected("tdx", "not_loopback")
# _get_gateway 抛错路径
metrics.record_snapshot_rejected("tdx", "not_ready")
```

### 5.2 tdx/realtime/gateway.py post_snapshot（L442-484）

根 span `tdx.snapshot.ingest` 包裹整个方法：
```python
async def post_snapshot(self, *, lease_token, stream_epoch, symbol, captured_at, native):
    tracer = trace.get_tracer("mist-datasource")
    with tracer.start_as_current_span("tdx.snapshot.ingest") as span:
        span.set_attribute("symbol", symbol)          # symbol 可作 span 属性（不是 label）
        span.set_attribute("captured_at", captured_at)
        log.info("ingest start source=tdx symbol=%s capturedAt=%s payload_bytes=%d",
                 symbol, captured_at, len(json.dumps(native)))
        try:
            ... 现有校验链（rfc3339 / safety / decode / owner-epoch / convergence）...
        except GatewayError as exc:
            span.add_event("rejected", {"reason": exc.code})
            span.set_status(trace.StatusCode.ERROR, exc.code)
            log.warn("ingest reject source=tdx reason=%s symbol=%s", exc.code, symbol)
            metrics.record_snapshot_rejected("tdx", _tdx_reason(exc.code))
            raise
        # 转换完成
        span.add_event("frame_built", {"schema": 2})
        log.info("frame built source=tdx symbol=%s frame_schema=2", symbol)
        metrics.record_snapshot_accepted("tdx")
        return {"accepted": True, "frame": frame}
```

**age 指标**：gateway 提取公开方法 `snapshot_age_seconds()`（现有 health() 里
lastSnapshotAgeSeconds 的计算逻辑提取复用），main.py 注册 observable 回调：
```python
# tdx/main.py
metrics.register_snapshot_age_callback(
    "tdx",
    lambda obs: obs.observe(gateway.snapshot_age_seconds(), {"source": "tdx"}),
)
```
age 在收集时实时算，不 set 0。

### 5.3 WS broadcast（tdx 路由层已有调用）

`ws_manager.broadcast(ws_realtime_snapshot("tdx", result["frame"]))` 之后（成功路径）：
```python
log.info("broadcast source=tdx clients=%d frame_bytes=%d", ws_manager.connection_count, len(...))
metrics.set_ws_clients("tdx", ws_manager.connection_count)
```

## 6. QMT 链路埋点

### 6.1 qmt/routes/bridge.py post_subscription_snapshot（L331-350）

对称：except 分支补日志 + 拒绝计数（ownership_error → reason，control_error → exc.reason）。

### 6.2 qmt/realtime/subscription.py accept_snapshot（L847-903）

根 span `qmt.snapshot.ingest`：
```python
async def accept_snapshot(self, ...):
    with tracer.start_as_current_span("qmt.snapshot.ingest") as span:
        span.set_attribute("subscription_id", subscription_id)
        log.info("ingest start source=qmt subscriptionId=%s capturedAt=%s", ...)
        # try 范围：前 4 个校验（owner/captured_at/subscription_id）会 raise；
        # per-symbol 循环在 try 外（循环不 raise，收集到 rejected 列表）
        try:
            self._owner_validator(owner_id, lease_token, generation)
            if not RFC3339_PATTERN.fullmatch(captured_at): raise ...
            if type(subscription_id) is not int: raise ...
        except QmtSubscriptionControlError as exc:
            span.add_event("rejected", {"reason": exc.reason})
            span.set_status(ERROR)
            log.warn("ingest reject source=qmt reason=%s", exc.reason)
            metrics.record_snapshot_rejected("qmt", exc.reason)
            raise
        # per-symbol 循环
        for raw_symbol, value in native.items():
            ... 现有 4 个拒绝分支 ...
            if rejected:
                span.add_event("symbol_rejected", {"symbol": symbol, "reason": reason})
                log.warn("symbol reject source=qmt symbol=%s reason=%s", symbol, reason)
                metrics.record_snapshot_rejected("qmt", reason)
        if accepted:
            span.add_event("frame_built", {"schema": 2, "accepted_symbols": len(accepted)})
            metrics.record_snapshot_accepted("qmt")
        else:
            log.warn("no accepted symbols, not publishing source=qmt")
            span.set_status(ERROR, "no accepted symbols")   # 全拒时标 ERROR
        return {"accepted": ..., "rejected": ...}
```

### 6.3 QMT publisher（qmt/main.py:68-72 publish_snapshot）

```python
def publish_snapshot(data):
    collector.record_snapshot(capturedAt)
    log.info("broadcast source=qmt clients=%d frame_bytes=%d", manager.connection_count, ...)
    metrics.set_ws_clients("qmt", manager.connection_count)
    manager.broadcast(ws_realtime_snapshot("qmt", data))
```

## 7. ws/manager.py broadcast 埋点

```python
async def broadcast(self, message):
    tracer = trace.get_tracer("mist-datasource")
    with tracer.start_as_current_span("ws.broadcast") as span:
        span.set_attribute("clients", len(connections))
        ...现有发送逻辑...
        if failed:
            span.set_attribute("send_failed", len(failed))
            span.add_event("send_failed", {"clients": [cid for cid, _ in failed]})
            for cid, _ in failed:
                log.warn("send failed source=... client=%s (evicted)", cid)
```

**source 推断（已验证）**：`WSMessage.provider` 字段存在（protocol.py:27），
`ws_realtime_snapshot("tdx", frame)` 构造时已带——broadcast 从 `message.provider`
读 source，**不加参数**。source 为 None 时不记日志/指标。

## 8. 指标 reason 枚举

**TDX**（路由层 GatewayError.code + gateway 内）：
`not_loopback | not_ready | invalid_timestamp | native_unsafe | native_invalid |
owner_not_locked | lease_invalid | epoch_mismatch | symbol_not_converged | decode_error`

**QMT**：`not_loopback | ownership_invalid | captured_at_invalid |
subscription_id_invalid | symbol_invalid | non_member | native_invalid | native_unsafe`

映射函数 `_tdx_reason(code)` / QMT 直接用 exc.reason。

## 9. 测试

### 9.1 tests/unit/test_otel.py 更新
- init_otel/instrument_app 拆分：no-op guard、幂等、force_flush 不 throw

### 9.2 tests/unit/test_logging_trace.py（新建）
- 有 active span 时日志行含 trace_id/span_id
- 无 span 时为 "-"

### 9.3 tests/unit/test_metrics.py（新建）
- 8 个指标存在（通过 meter 注册表断言）
- reason 有界（TDX 10 个 / QMT 8 个）

### 9.4 tests/unit/test_gateway_tracing.py（新建）
用 OTel SDK 的 `InMemorySpanExporter` + SimpleSpanProcessor（真实断言，非 mock）：
- 合法 snapshot → 断言根 span `tdx.snapshot.ingest` 存在、status OK、frame_built event、
  accepted 计数
- 每个拒绝分支（symbol_not_converged 等）→ 断言 rejected event + status ERROR + 计数

### 9.5 tests/unit/test_subscription_tracing.py（新建）
InMemorySpanExporter：
- 部分拒绝 → symbol_rejected event + 计数 + accepted 部分
- 全拒 → ERROR + no-accepted 日志

### 9.6 tests/unit/test_manager_tracing.py（新建）
InMemorySpanExporter：
- send 失败 → send_failed event + warn 日志 + eviction

### 9.7 tests/unit/test_qmt_startup.py（新建，C1）
- 构造 ambiguous observation 文件 → 断言 error 日志 + InMemorySpanExporter 见
  qmt.startup ERROR span + force_flush 被调用（monkeypatch force_flush）

### 9.8 现有 490 测试无回归

## 10. mock 验证（D7 闭环）

```
cd mist-datasource && bash tools/mock-env/run-mock.sh
  # 需要 datasource 启动带 OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:5080
  # （run-mock.sh 的 uvicorn 启动命令加 env，或 .env.mock 里加）
python3 tools/mock-env/mock-drive.py --source tdx --frames 5
curl -sS -u "root@mist.local:Mist@2026!Observe" \
  "http://127.0.0.1:5080/api/default/_search" (POST + SQL 查 traces)
  # 预期：tdx.snapshot.ingest span 存在
# 停注入 → age 增长 + 无新 ingest span
# C1：构造 context-rebuild-observation.json + .processing → qmt 启动 → 日志 error
```

**run-mock.sh 改动**：datasource 启动命令加 OTel env
（`OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:5080` +
`OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic ...`），qmt 同。

## 11. 验证命令

```bash
cd mist-datasource
uv run ruff check . && uv run pyright
uv run pytest tests/ -m "not live"    # 490 + 新增全绿，覆盖率 ≥85%
openspec validate instrument-datasource-bridge-ingest --strict
bash tools/mock-env/run-mock.sh && bash tools/mock-env/mock-verify.sh
```

## 12. 提交

- mist-datasource 分支 `feat/instrument-bridge-ingest` 提交推送
- 不合并 master（等 O1 backend 埋点一起合 + 部署）

---

## 风险与注意

1. **OTel 1.44 有原生 Gauge**：直接 create_gauge；age 用 create_observable_gauge。
   **仪器注册必须一次**：同名重复 create 抛 DuplicateMetricError——init_metrics()
   在 init_otel() 后调一次，辅助函数只引用已注册仪器
2. **instrument_app 幂等**：FastAPIInstrumentor 自带 `_is_instrumented_by_opentelemetry`
   标志，重复调用安全；但 init_otel 的 `_configured` 标志要独立（provider 层）
3. **span 属性 vs 指标 label**：symbol/subscriptionId 只作 **span attribute**（可查询），
   绝不作 **metric label**（基数爆炸）——spec Requirement 7 强制
4. **broadcast 的 source 推断**：manager 是共用组件，source 参数可选，缺省不记日志
5. **force_flush 在 re-raise 前**：C1 路径顺序（日志 → span ERROR → force_flush → raise）
   不可颠倒
6. **uvicorn 启动失败时模块级异常**：`app = _build_app_with_startup_trace()` 抛错 →
   uvicorn 打印 traceback → 进程退出——force_flush 已完成
