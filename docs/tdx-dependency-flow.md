# TDX 模块 Python 方法依赖流程分析

> 本文档梳理 `mist-datasource` 仓库中 TDX（通达信）部分的 Python 方法与函数依赖流程，重点区分**底层依赖 `tqcenter.tq` SDK** 的方法与**走 HTTP/JSON-RPC 通道**（不依赖 tq）的方法。

## 目录

- [1. 架构总览](#1-架构总览)
- [2. 近期改动摘要](#2-近期改动摘要)
- [3. 分层结构](#3-分层结构)
- [4. 调用链对照表](#4-调用链对照表)
- [5. 底层 tq SDK 依赖（adapter 层）](#5-底层-tq-sdk-依赖adapter-层)
- [6. HTTP 通道（datasource/provider 层）](#6-http-通道datasourceprovider-层)
- [7. 能力清单（capabilities.py）](#7-能力清单capabilitiespy)
- [8. WebSocket 订阅链路](#8-websocket-订阅链路)
- [9. 运行时接线（main.py lifespan）](#9-运行时接线mainpy-lifespan)
- [10. 依赖判定汇总](#10-依赖判定汇总)
- [11. 孤儿代码与遗留说明](#11-孤儿代码与遗留说明)

---

## 1. 架构总览

TDX 部分并非"单链路"架构，而是存在 **三条互不交叉的调用链**：

| 调用链 | 涉及路由 | 路径 | 底层依赖 |
|--------|---------|------|---------|
| **① 旧式 REST** | `/api/tdx/*`（33 个端点） | `route → adapter` | `tqcenter.tq`（进程内 SDK） |
| **② 新式契约 REST** | `/v1/*` | `route → provider → http_client` | HTTP/JSON-RPC（httpx） |
| **③ 实时 WebSocket** | `/ws/quote/{client_id}` | `route → subscription(+adapter) + bridge + collector` | 订阅走 tq SDK，快照拉取走 HTTP |

**核心结论：**

- **底层依赖 tq SDK** 的方法 = 调用链 ① 全部 + 调用链 ③ 的订阅部分
- **走 HTTP（不依赖 tq）** 的方法 = 调用链 ② 全部 + 调用链 ③ 的快照拉取部分
- `tdx/services/tdx_service.py` 的 `TDXService` 是**孤儿代码**——全局搜索确认无任何 route 引用，也未挂到 `app.state`

---

## 2. 近期改动摘要

> 本节对照最近一轮 datasource / routes 改动，说明**哪些变了、哪些没变**。架构骨架（三条调用链）不变。

### 不变的部分

- **三条调用链的拓扑完全不变**：`/api/tdx/*` 仍走 adapter，`/v1/*` 仍走 provider→HTTP，`/ws/*` 仍走 subscription+adapter。
- **`tdx_service` 仍是孤儿**：grep 全仓库确认零引用，未挂到 `app.state`（见 [第 11 节](#11-孤儿代码与遗留说明)）。
- **WS 订阅链路三组件**（subscription / bridge / collector）协作关系不变。
- **`main.py` lifespan 启动/关闭顺序、`app.state` 键集合**不变。

### 变化的部分

| 变化 | 影响范围 | 性质 |
|---|---|---|
| **路由依赖注入重构** | `tdx/routes/*` 与 `qmt/routes/*` 全部路由 | 纯形式重构：`_get_adapter` + 内联 `if not adapter: 503` → `require_tdx_adapter`（集中抛 503）。**调用链不变** |
| **`tdx/routes/dependencies.py` 新增 `require_tdx_adapter`** | 依赖层 | 见 [第 4 节](#4-调用链对照表) |
| **provider 大幅扩展（~30KB → 48KB / 1415 行）** | `src/datasource/tdx_provider.py` | 新增大量查询方法 + 完整公式系列（`format/set/get_formula_*`、`execute_formula[_batch]`、`get_formula_list/info`）。方法表见 [第 6.2 节](#62-provider-方法清单全部走-http不碰-adaptertq) |
| **新增 `capabilities.py`** | `src/datasource/capabilities.py` | provider 能力清单，供 `/providers` 端点用。详见 [第 7 节](#7-能力清单capabilitiespy) |

---

## 3. 分层结构

| 层 | 文件 | 职责 | 是否依赖 tq SDK |
|---|---|---|---|
| **路由层** | `tdx/routes/*.py` | HTTP / WebSocket 端点 | 间接（①③）/ 不间接（②） |
| **服务层** | `tdx/services/tdx_service.py` | 复合业务（**孤儿，未接线**） | 依赖 adapter |
| **datasource 层** | `src/datasource/tdx_provider.py` | HTTP 通道数据访问 | 否（走 httpx） |
| | `src/datasource/tdx_http_client.py` | HTTP/JSON-RPC 客户端 | 否（走 httpx） |
| | `src/datasource/tdx_subscription.py` | WS 订阅协调器 | 是（调 `adapter.subscribe_hq`） |
| | `src/datasource/tdx_bridge.py` | 订阅内存状态容器 | 否（纯内存） |
| | `src/datasource/tdx_collector.py` | 脏标记 → 定时拉快照 | 否（走 provider HTTP） |
| | `src/datasource/tdx_normalization.py` | 数据归一化纯函数 | 否 |
| | `src/datasource/tdx_models.py` | Pydantic 模型 | 否 |
| | `src/datasource/capabilities.py` | provider 能力清单（元数据，**新增**） | 否 |
| | `src/datasource/contracts.py` | 公共基类/时区/错误模型 | 否 |
| **adapter 层** | `src/adapter/tdx/client.py` | **直接对接 tq SDK 的唯一入口** | 是 |
| | `src/adapter/mock/tdx_mock.py` | macOS 开发替身 | 否 |

---

## 4. 调用链对照表

| 路由文件 | 前缀 | 调用链 | 依赖注入函数 |
|---|---|---|---|
| `market.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `stock.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `financial.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `value.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `sector.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `etf.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `client.py` | `/api/tdx` | `route → adapter` | `require_tdx_adapter` |
| `v1.py` | `/`（路径含 `/v1/`） | `route → provider → http_client` | `get_tdx_provider` |
| `ws.py` | `/ws` | `route → subscription_client(+adapter) + bridge + collector` | `get_ws_manager` / `get_tdx_bridge` / `get_tdx_subscription_client` |

> `tdx/routes/dependencies.py` 提供 6 个 getter：
> - `get_tdx_adapter` —— 读 `tdx_adapter`，可能返回 `None`（路由层一般不直接用）
> - `require_tdx_adapter` —— **新增**。在 `get_tdx_adapter` 基础上判空，为 `None` 直接抛 `HTTPException(503)`。`/api/tdx/*` 七个路由统一改用它，消除了原先每个端点内联的 `if not adapter: 503` 样板
> - `get_tdx_provider` / `get_tdx_bridge` / `get_tdx_subscription_client` / `get_ws_manager`
>
> **没有 `_get_service`**——`tdx_service` 不参与依赖注入。

---

## 5. 底层 tq SDK 依赖（adapter 层）

`src/adapter/tdx/client.py` 是整个仓库里**唯一直接调用 `tqcenter.tq` 的地方**。

### 5.1 核心设计

```python
TDXAdapter(MarketDataAdapter)
  ├─ _load_tq_module(sdk_path)   # importlib 加载 tqcenter.py，取出 tq 类对象
  ├─ _call_tq(name, *args)       # ★ 所有业务方法访问 SDK 的唯一入口
  │     └─ asyncio.to_thread(getattr(self._tq, name), *args)  # 同步 SDK → 异步包装
  ├─ initialize()                # tq.initialize(init_path) + 启动心跳任务
  ├─ _heartbeat_loop()           # 每 10 分钟调 get_stock_list 保活（防 30 分钟断连）
  └─ shutdown()                  # 停心跳、置 self._tq = None
```

关键点：tq 对象通过 `module.__dict__["tq"]` 取出后当作命名空间直接调静态方法（`getattr(self._tq, method_name)`），**不实例化**，仓库里**没有 `TQLoader`** 这个名字。

### 5.2 直接调用 tq SDK 的方法清单

| 分组 | 方法 | 对应 tq API |
|---|---|---|
| **连接/基础设施** | `_load_tq_module`（导入）, `_call_tq`（桥接）, `_heartbeat_loop`, `initialize` | `tq.initialize` |
| **行情** | `get_stock_list`, `get_stock_list_in_sector`, `get_market_data`(+`price_df`), `get_market_snapshot`, `get_divid_factors`, `get_gb_info`, `get_trading_dates`, `refresh_cache`, `refresh_kline`, `download_file` | `tq.<同名>` |
| **股票信息** | `get_stock_info`, `get_more_info`, `get_relation` | `tq.<同名>` |
| **财务/交易值** | `get_financial_data`, `get_financial_data_by_date`, `get_gp_one_data`, `get_bkjy_value[_by_date]`, `get_gpjy_value[_by_date]`, `get_scjy_value[_by_date]` | `tq.<同名>` |
| **板块** | `get_sector_list`, `get_user_sector`, `send_user_block` | `tq.<同名>`（`send_user_block` 含 `show=True`） |
| **ETF/可转债** | `get_kzz_info`, `get_ipo_info`, `get_trackzs_etf_info` | `tq.get_cb_info` / `tq.get_ipo_info` / `tq.get_trackzs_etf_info` |
| **订阅** | `subscribe_hq`, `unsubscribe_hq`, `get_subscribe_list` | `tq.subscribe_hq` / `tq.unsubscribe_hq` / `tq.get_subscribe_hq_stock_list` |
| **客户端控制** | `exec_to_tdx` | `tq.exec_to_tdx` |

### 5.3 未实现（`raise NotImplementedError`，不调用 SDK）

下列方法签名预留但函数体抛异常：

- **交易类**：`order_stock`, `cancel_order_stock`, `query_stock_orders`, `query_stock_positions`, `query_stock_asset`, `stock_account`
- **公式类**：`formula_format_data`, `formula_set_data`, `formula_set_data_info`, `formula_get_data`, `formula_zb`, `formula_exp`, `formula_xg`, `formula_process`, `formula_process_mul_xg`, `formula_process_mul_zb`
- **客户端通信类**：`send_message`, `send_file`, `send_warn`, `send_bt_data`, `print_to_tdx`
- **板块管理**：`create_sector`, `delete_sector`, `rename_sector`, `clear_sector`

### 5.4 mock 切换

工厂函数 `create_tdx_adapter()` 位于 `src/adapter/__init__.py`（**不在** `tdx/__init__.py`）：

```python
def create_tdx_adapter() -> TdxDataAdapter:
    if settings.is_production:          # APP_ENV=production
        from src.adapter.tdx.client import TDXAdapter
        return TDXAdapter()             # 真实 adapter（延迟导入）
    else:
        return TDXMockAdapter()         # 开发态替身，读 tests/fixtures/tdx/*.json
```

- 决策依据：`settings.is_production`（`src/core/config.py`，`app_env == "production"`）
- 真实 adapter 延迟导入，非生产环境根本不触发 tq SDK 加载逻辑
- 即使切到生产 adapter，`initialize()` 仍要求 `settings.tdx.sdk_path`（`TDX_SDK_PATH` 环境变量）非空

---

## 6. HTTP 通道（datasource/provider 层）

`TdxDatasourceProvider`（`src/datasource/tdx_provider.py`）+ `TdxHttpClient`（`tdx_http_client.py`）是**完全独立于 tq SDK 的另一条通道**，用 `httpx` POST JSON-RPC 到 `settings.tdx.http_url`。

### 6.1 底层客户端 `TdxHttpClient`

| 成员 | 用途 |
|---|---|
| `TdxHttpError(*, code, message, retryable, details)` | HTTP/JSON-RPC 错误异常 |
| `TdxHttpClient.__init__(base_url, timeout, http_client)` | 创建客户端；`http_client` 为空则自建 `httpx.AsyncClient` |
| `TdxHttpClient.call(method, params=None)` | **核心方法**：组装 JSON-RPC 2.0 payload，POST，校验状态/结构/error，返回 `body["result"]` |
| `TdxHttpClient.aclose()` | 关闭 httpx client |
| `_json_rpc_error_retryable(error)` | 根据 JSON-RPC error code 判断是否可重试 |

### 6.2 Provider 方法清单（全部走 HTTP，不碰 adapter/tq）

构造：`__init__(client=None)` —— `self.client = client or TdxHttpClient(settings.tdx.http_url)`。

所有方法的统一形态：`self.client.call("tq方法名", params)` → `normalize_*` 纯函数转换。

| 类别 | 方法 |
|---|---|
| **行情** | `get_bars`, `collect_recent_bars`, `get_snapshots`, `get_price_volume` |
| **日历/证券** | `get_trading_dates`, `get_securities`, `get_security_info`(两次 RPC), `get_security_relations` |
| **板块** | `get_sector_list`, `get_sector_members` |
| **股本/分红/转债/ETF** | `get_share_capital[_by_date]`, `get_dividend_factors`, `get_convertible_bond_info`, `get_tracking_etfs`, `get_ipo_info` |
| **财务** | `get_financial_data[_by_date]`, `get_single_finance_values` |
| **交易聚合** | `get_stock_trade_aggregate[_by_date]`, `get_sector_trade_aggregate[_by_date]`, `get_market_trade_aggregate[_by_date]` |
| **公式** | `format_formula_data`, `set_formula_data`, `set_formula_data_info`, `get_formula_data`, `get_formula_list`, `get_formula_info`, `execute_formula(kind,...)`, `execute_formula_batch`, `call_formula` |
| **工具** | `raw_call`（透传任意 RPC）, `health`（对 600519.SH 发 snapshot 探测）, `aclose` |

> ⚠️ **新旧接口并存**：`provider.get_bars` 和 `adapter.get_market_data` 名字不同、通道不同、归一化逻辑不同，但底层最终都连到同一个 TDX 后端——provider 走 HTTP 网关，adapter 走进程内 SDK。

### 6.3 Provider 内部辅助函数（纯转换，不依赖外部）

- **归一化**：`_normalize_trading_date`, `_normalize_security_item`, `_normalize_security_info`, `_normalize_sector_item`, `_normalize_price_volume_item`, `_normalize_relation_items`, `_normalize_ipo_item`, `_normalize_share_capital_item`, `_normalize_dividend_factor_item`, `_normalize_convertible_bond_item`, `_normalize_tracking_etf_item`
- **财务/交易聚合**：`_normalize_financial_data_items`, `_normalize_single_finance_value_items`, `_normalize_trade_aggregate_items`
- **公式**：`_normalize_formula_*` 系列
- **拆包/查找**：`_unwrap_tdx_value`, `_native_mapping`, `_native_sequence`, `_native_record`, `_native_items`, `_native_item_for_symbol`, `_record_for_code`, `_lookup_symbol_field`, `_lookup_aggregate_value`, `_code_candidates`, `_first_native_value`
- **工具**：`_optional_float`, `_optional_int`, `_optional_bool`, `_scalar_value`, `_to_tdx_native_date`, `_raise_for_native_error`, `_effective_formula_timeout_ms`, `_payload_formula_timeout_ms`
- **异常类**：`TdxFormulaRequestLimitError`, `TdxFormulaTimeoutError`, `TdxNativeError`, `TdxSymbolNotFoundError`

---

## 7. 能力清单（capabilities.py）

`src/datasource/capabilities.py` 是这一轮**新增**的文件，定义 provider 自描述能力清单，供 `GET /providers` 端点（`v1.py`）返回。它**不参与数据调用**，纯元数据。

### 7.1 数据结构

| 模型 | 用途 |
|---|---|
| `ProviderCapabilityUnsupported` | 异常：provider 不支持某能力时抛，被 `v1.py` 的 `_call_provider` 捕获转成错误信封 |
| `ProviderCapability` | 单项能力：`family` / `status(supported\|planned\|unsupported)` / `stability` / `providerMethods` / `unsupportedReason` |
| `ProviderManifest` | 单个 provider 的清单：`id` / `name` / `status` / `capabilities[]` |

### 7.2 两个能力字典

- `TDX_CAPABILITY_STATUSES`（46-160 行）：约 30 个能力族，绝大部分 `supported`，少数 `planned`（`benchmarks` / `security-search` / `reference-data` / `instrument-data`）
- `QMT_CAPABILITY_STATUSES`（162-239 行）：绝大多数 `unsupported` 或 `planned`（QMT 尚未实现）

`build_provider_manifests(*, tdx_status)` 据此构造 TDX + QMT 两个 `ProviderManifest`。

### 7.3 ⚠️ 易误读点：`providerMethods` 字段语义

`TDX_CAPABILITY_STATUSES` 里每个能力条目的 `providerMethods` 字段（第三元），列出的全是 **tq SDK 底层方法名**，例如：

```python
"bars":             (..., ["get_market_data"], ...),
"snapshots":        (..., ["get_market_snapshot"], ...),
"websocket-subscriptions": (..., ["subscribe_hq", "unsubscribe_hq", "get_subscribe_hq_stock_list"], ...),
```

但 `/v1/*` 路由实际调的是 **provider 方法名**（`get_bars` / `get_snapshots` / `subscribe`），与清单字段**不对应**。这个清单描述的是"该能力族在底层由哪些 tq 原生方法支撑"，而非"provider 暴露哪些方法"。读这份清单时注意区分两层命名。

---

## 8. WebSocket 订阅链路

### 8.1 三组件协作

| 组件 | 文件 | 职责 | 依赖 adapter? |
|---|---|---|---|
| `TdxSubscriptionClient` | `tdx_subscription.py` | 订阅协调器 | **是**（调 `adapter.subscribe_hq/unsubscribe_hq`） |
| `TdxBridge` | `tdx_bridge.py` | 运行时内存状态（leader 选举、订阅集合、事件队列、回调计数） | 否（纯内存） |
| `TdxMinuteCollector` | `tdx_collector.py` | 脏标记 → 定时拉快照 | 否（走 provider HTTP） |

### 8.2 `TdxSubscriptionClient` 方法（datasource 层中唯一真正依赖 adapter 的组件）

| 方法 | 用途 | 调 adapter? |
|---|---|---|
| `subscribe(symbols)` | 增量订阅：超限拒绝 → `adapter.subscribe_hq(to_subscribe, callback)` → `bridge.mark_active` | 是 |
| `sync(symbols)` | 全量同步：算 diff → 先退订再订阅 | 是 |
| `unsubscribe(symbols=None)` | 退订（None 全部）→ `adapter.unsubscribe_hq` | 是 |
| `_on_quote_update(payload)` | SDK 行情回调入口：解析 → 校验 Code → `bridge.record_quote_callback` → `collector.mark_dirty_from_callback` | 否（纯本地，但由 adapter 触发） |

> 每个公开方法在 `except` 分支都会尽力把 adapter 的订阅状态恢复到 `previous_active` 并重新绑定回调，避免 bridge 状态与 SDK 实际订阅状态不一致。

### 8.3 `TdxBridge`（纯内存状态容器）

注意它叫 "bridge" 但**与 adapter 无关**，名字易引起误解。doc string 明确："Runtime-only bridge state shared by TDX WebSocket connections."

核心成员：`claim_leader`, `disconnect`, `plan_sync`, `mark_active`, `enqueue_bar`, `record_callback`, `record_quote_callback`, `record_queue_depth`, `report_backpressure`, `health`, `make_ready_message`, `make_error_message`。

### 8.4 `TdxMinuteCollector`（两条通道的汇合点）

- **回调入口**（SDK 通道）：`mark_dirty_from_callback(payload)` —— 从 SDK 回调线程经 `call_soon_threadsafe` 把 symbol 标记为 dirty
- **采集循环**（HTTP 通道）：`collect_dirty_once()` —— 取 dirty 符号 → 过滤活跃符号 → `provider.get_snapshots(symbols)`（**HTTP**）→ 发布

调用链：
```
adapter 回调 → _on_quote_update → collector.mark_dirty_from_callback
                                            │
collect_dirty_once → provider.get_snapshots(HTTP) → snapshot_publisher → ws_manager.broadcast
```

### 8.5 归一化与模型（纯数据）

- `tdx_normalization.py`：`normalize_symbol`, `to_tdx_code`, `to_tdx_http_code`, `beijing_iso`, `normalize_number`, `normalize_native_key`, `native_value`, `normalize_tdx_bar_rows`, `normalize_tdx_snapshot` 等——**零 adapter 依赖的纯函数**
- `tdx_models.py`：`TdxBar`, `TdxSnapshot`, 各类 `*QueryRequest`/`*ExecutionRequest`, `TdxFormulaOperationResult`, `RawTdxCallRequest`, `TdxWsMessage`——纯 Pydantic 模型

---

## 9. 运行时接线（main.py lifespan）

启动顺序严格按依赖拓扑（`tdx/main.py`）：

```
1. tdx_adapter = create_tdx_adapter(); await adapter.initialize()
2. tdx_provider = TdxDatasourceProvider()                         # 独立 HTTP 通道
3. tdx_bridge = TdxBridge(queue_max_size, max_subscriptions)      # WS 状态黑板
4. tdx_collector = TdxMinuteCollector(provider, bridge, ...)      # 横跨两通道
5. tdx_subscription_client = TdxSubscriptionClient(adapter, bridge, collector, ...)
6. await collector.start()
7. _sync_app_state(app)
```

挂到 `app.state` 的对象（`dependencies.py` 读取的键）：

| app.state 键 | 类型 |
|---|---|
| `tdx_adapter` | `TDXAdapter` / `TDXMockAdapter` |
| `tdx_provider` | `TdxDatasourceProvider` |
| `tdx_bridge` | `TdxBridge` |
| `tdx_collector` | `TdxMinuteCollector` |
| `tdx_subscription_client` | `TdxSubscriptionClient` |
| `ws_manager` | `ConnectionManager` |

> **注意：`tdx_service` 没有挂上去**——再次印证 service 层未接入运行时。

关闭顺序（L125-163）逆序清理：`collector.stop()` → 各对象置空 → `provider.aclose()` → `adapter.shutdown()`。每步用 `owned_*` 标记判断"是否本进程创建"，只关停自有实例。

---

## 10. 依赖判定汇总

### 🟦 底层依赖 tq SDK 的方法（通过 TDXAdapter）

- **adapter 层**：`TDXAdapter` 的所有非 `NotImplementedError` 方法（见 [5.2](#52-直接调用-tq-sdk-的方法清单)）
- **subscription 层**：`TdxSubscriptionClient.subscribe / sync / unsubscribe`
- **路由层**：`/api/tdx/*` 全部 33 端点 + `/ws/quote` 的订阅动作

### 🟩 走 HTTP（替代 tq）的方法

- **provider 层**：`TdxDatasourceProvider` 全部 30+ 方法（统一 `self.client.call(...)`）
- **collector**：`collect_dirty_once`（间接调 `provider.get_snapshots`）
- **路由层**：`/v1/*` 全部端点 + WS 链路里的快照拉取

### ⬜ 纯数据/内存（不依赖任何外部）

- `tdx_normalization.py`、`tdx_models.py`、`tdx_bridge.py` 全部
- `tdx_http_client.py`（依赖 httpx，但不依赖 adapter/tq）
- `tdx_provider.py` 内所有 `_normalize_*` / `_unwrap_*` / `_native_*` 工具函数

### 🔴 孤儿代码

- `tdx/services/tdx_service.py`：`TDXService.get_sector_overview` 无任何 route 引用，即便被调也是 `route → service → adapter`，不经过 provider

---

## 11. 孤儿代码与遗留说明

### 11.1 `TDXService`（services/tdx_service.py）

- 文件 docstring（第 6-8 行）自述："大部分 routes 直接调用 adapter 方法，service layer 主要用于 DataFrame 序列化和复合业务逻辑"
- 定义了模块级单例 `tdx_service = TDXService()`，但全局搜索确认**无任何 route import**
- 唯一方法 `get_sector_overview(sector)` 组合调用 `adapter.get_stock_list_in_sector` + `adapter.get_market_data`，即便被调也是 `route → service → adapter`，不经过 provider
- 辅助函数 `_serialize_result` 递归把 pandas DataFrame 转 JSON 结构，同样无人调用

### 11.2 `tdx/config.py`

仅从 `src.core.config.settings` 抽取 `INSTANCE_NAME` / `HOST` / `PORT`，**未被 main.py 或 routes 使用**（main.py 直接用 `settings.tdx.*`）。近乎废弃的薄封装。

### 11.3 新旧接口并存的现状

| 能力 | 旧式（`/api/tdx/*`） | 新式（`/v1/*`） |
|---|---|---|
| K 线 | `adapter.get_market_data` | `provider.get_bars` |
| 快照 | `adapter.get_market_snapshot` | `provider.get_snapshots` |
| 财务 | `adapter.get_financial_data` | `provider.get_financial_data` |
| 公式 | （未实现） | `provider.execute_formula` |
| 板块成分 | `adapter.get_stock_list_in_sector` | `provider.get_sector_members` |

两套接口最终连同一 TDX 后端，但通道、归一化、响应信封（`/v1/*` 用 `ResponseEnvelope` 统一包装）均不同。
