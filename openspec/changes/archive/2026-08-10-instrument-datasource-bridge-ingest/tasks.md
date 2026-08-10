# Tasks: instrument-datasource-bridge-ingest

## 1. OTel provider 初始化重构（C1 直接覆盖的前提）

- [x] 1.1 `src/core/otel.py`：拆 `init_otel(service_name)`（只初始化 provider+exporter，
      no-op guard + 幂等）+ `instrument_app(app)`（FastAPIInstrumentor）。
- [x] 1.2 `tdx/main.py`：`setup_logging()` 后调 `init_otel("tdx-datasource")`，
      `app = create_tdx_app()` 后 `instrument_app(app)`。
- [x] 1.3 `qmt/main.py`：同上（`init_otel("qmt-datasource")`）。
- [x] 1.4 更新 `tests/unit/test_otel.py`：覆盖 init_otel/instrument_app 拆分 + no-op guard + 幂等。

## 2. 日志基础设施：trace_id 注入

- [x] 2.1 `src/core/logging.py`：结构化 formatter 注入 trace_id/span_id
      （从 `trace.get_current_span()` 读 context，无 span 时省略）。
- [x] 2.2 单测：有/无 active span 两种情况下日志行格式。

## 3. datasource 指标定义（8 个）

- [x] 3.1 新建 `src/datasource/metrics.py`：OTel Meter 定义 8 个指标
      （snapshot_age/accepted/rejected/bridge_ready/owner_stale/control_total/ws_clients/startup_ok）。
- [x] 3.2 单测：指标存在 + reason 枚举有界 + 不携带 symbol/ownerId。

## 4. TDX snapshot 链路埋点

- [x] 4.1 `tdx/realtime/gateway.py` `post_snapshot`：
      - 根 span `tdx.snapshot.ingest`（进入时开始，返回/抛错时结束）
      - 3 个生命周期日志：进入（symbol/capturedAt/bytes）、转换完成、拒绝
      - 每个判断点拒绝：span event `rejected{reason}` + set_status(ERROR) + warn 日志
        + `snapshot_rejected_total{reason}` 计数
      - 成功：`snapshot_accepted_total` 计数 + `snapshot_age_seconds` 更新来源不变
- [x] 4.2 `tdx/routes/bridge.py`：loopback/not_ready 拒绝点埋点（span event + 日志 + 计数）。

## 5. QMT snapshot 链路埋点

- [x] 5.1 `qmt/realtime/subscription.py` `accept_snapshot`：
      - 根 span `qmt.snapshot.ingest`
      - per-symbol accept/reject 循环：每个拒绝分支 span event + warn 日志 + 计数
      - publish gate：无 accepted 时日志 `[warn] no accepted symbols, not publishing`
- [x] 5.2 `qmt/routes/bridge.py`：loopback/ownership 拒绝点埋点。

## 6. WS broadcast 埋点（静默丢弃点修复）

- [x] 6.1 `ws/manager.py` `broadcast`：
      - 子 span `ws.broadcast`（clients/send_failed/耗时）
      - per-client send 失败：warn 日志 + span event（eviction 可见）

## 7. QMT 启动失败直接覆盖（C1）

- [x] 7.1 `qmt/main.py`：
      - `create_qmt_app()` 用 try/except 包裹，调用前开始 `qmt.startup` span
      - 成功：span status OK + `mist_datasource_startup_ok{source="qmt"}=1`
      - 失败：error 日志（带 observation 路径 + processing marker）→ span
        set_status(ERROR) + record_exception → **provider.force_flush()（同步）**
        → 重新 raise
      - `consume_rebuilt_context_observation` 检查点日志（进入 + 失败）
- [x] 7.2 单测：构造 ambiguous observation 文件 → 断言 error 日志 + span ERROR +
      force_flush 被调用（用 mock tracer/span 断言，不真连 OpenObserve）。

## 8. 验证

- [x] 8.1 `uv run ruff check .` + `uv run pyright` 全绿。
- [x] 8.2 `uv run pytest tests/ -m "not live"` 全绿（覆盖率 ≥85% 门禁）。
- [x] 8.3 `openspec validate instrument-datasource-bridge-ingest --strict`。
- [x] 8.4 mock 验证闭环（D7）：
      - 注入 → OpenObserve 见 `tdx.snapshot.ingest` span + accepted 增长 + age 正常
      - 停注入（A2）→ age 增长 + ingest span 消失 + accepted 停止
      - C1：构造 observation 文件 → qmt 启动 → 日志 error + startup span ERROR

## 9. 提交（不合并 master）

- [x] 9.1 mist-datasource 仓提交推送（实际直接 master：fb38428 等，未开分支）。
- [x] 9.2 已随 O1 一起部署验证（2026-08-10，生产 OO 见 tdx.snapshot.ingest/ws.broadcast spans）。
