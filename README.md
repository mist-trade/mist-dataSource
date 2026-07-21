# Mist-Datasource

数据源桥接层 - 将通达信 (TDX) 与大 QMT 内置 Python 数据能力包装为 HTTP/WebSocket 服务。

## 项目定位

mist-datasource 是 NestJS 后端的**数据源桥接层**，核心职责：

- 将通达信 (TDX) 与大 QMT 内置 Python 数据能力包装为 HTTP/WebSocket 服务
- 通过 WebSocket 将实时行情推送到 NestJS 后端
- 保留 TDX 与 QMT 的原生历史数据边界，只在各自的实时传输内维护稳定契约

**不是**一个通用的 WebSocket 微服务平台，而是一个**适配器层 (Adapter Layer)**。

实时链路按模式互斥启用：TDX 默认为 `legacy`，可切换到
`builtin_experimental`；QMT 默认为 `off`，可切换到
`builtin_experimental`。实验模式只处理实时快照，不改变 TDX `:17709`
HTTP 历史链路或 QMT native bridge 历史数据形状。

## 架构总览

```
通达信终端 (Windows)          大 QMT 客户端 (Windows)
      │                              │
      │ tqcenter SDK                 │ 内置 Python bridge
      ▼                              ▼
┌─────────────┐              ┌─────────────┐
│  Instance 1 │              │  Instance 2 │
│  TDX Adapter│              │ QMT DataSrc │
│  Port: 9001 │              │  Port: 9002 │
│  FastAPI     │              │  FastAPI     │
└──────┬──────┘              └──────┬──────┘
       │ WebSocket                  │ WebSocket
       ▼                            ▼
┌──────────────────────────────────────────┐
│           NestJS Backend                 │
│  mist(8001) / saya(8002) / chan(8008)    │
└──────────────────────────────────────────┘
```

## 技术栈

| 项目 | 选型 | 原因 |
|------|------|------|
| Python | datasource 3.12+ / TDX 3.7 / QMT 3.6 | 内置脚本必须兼容各终端自带解释器 |
| 包管理 | uv | 速度快，lockfile 可靠 |
| 框架 | FastAPI | 异步支持好，自动 OpenAPI 文档 |
| 配置 | pydantic-settings | 类型安全的环境变量管理 |
| 代码质量 | ruff + pyright + pre-commit | 统一工具链 |
| 测试 | pytest + pytest-asyncio + httpx | 异步测试支持，ASGI transport |

## 端口规划

| Instance | 端口 | 用途 |
|----------|------|------|
| tdx | 9001 | TDX 适配器 |
| qmt | 9002 | QMT datasource |

## 快速开始

### 安装依赖

```bash
# 使用 uv (推荐)
pip install uv
uv sync

# 或使用 pip
pip install -e ".[dev]"
```

### 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件配置参数
```

### 启动服务

```bash
# macOS 开发 - 单独启动
uv run uvicorn tdx.main:app --port 9001 --reload
uv run uvicorn qmt.main:app --port 9002 --reload

# 或使用启动脚本
./scripts/start_all.sh   # 启动所有服务
./scripts/stop_all.sh    # 停止所有服务
```

### 运行测试

```bash
# 运行所有测试
uv run pytest

# 跳过需要 Windows + TDX 终端的测试
uv run pytest -m "not live"

# 运行单个测试
uv run pytest tests/integration/test_tdx_routes.py::test_get_stock_list

# 带覆盖率
uv run pytest --cov=src --cov=tdx --cov=qmt
```

## 跨平台策略

### macOS 开发
- 使用合成 fixture 和 ASGI 测试验证 REST、WebSocket 与模式门禁
- 不声称本机具备 TDX/QMT 终端能力，也不以随机行情替代 Windows 实机证据

### Windows 生产
- `APP_ENV=production`；TDX 历史接口走官方 `:17709`，QMT 历史 bars 由内置脚本执行 `get_market_data_ex`
- TDX 实时链路固定由终端内置 bridge 持有，不再存在 datasource 进程内 SDK adapter 或 mode switch
- 前置条件：相应终端已启动；内置策略脚本只能由操作员手工注册和启停
- WinSW datasource 与桌面终端恢复由 `mist-deploy` 仓库分别管理

## 目录结构

```
mist-datasource/
├── docs/references/          # TDX/QMT datasource 设计、覆盖矩阵和 smoke 参考
├── src/                      # 共享核心代码
│   ├── core/                 # 配置、日志、异常
│   │   ├── config.py         # pydantic-settings 配置
│   │   ├── logging.py        # 日志配置
│   │   └── exceptions.py     # 自定义异常
│   ├── datasource/           # TDX/QMT provider 与实时 gateway
│   │   ├── tdx/              # TDX V1 与 builtin realtime gateway
│   │   └── qmt/              # QMT native bridge datasource
│   └── ws/                   # WebSocket 管理
│       ├── protocol.py       # WSMessage 消息协议
│       └── manager.py        # ConnectionManager 连接管理
├── tdx/                      # TDX 适配器服务 (Port 9001)
│   ├── main.py               # FastAPI 应用入口
│   ├── routes/               # REST API 路由
│   │   ├── v1/               # normalized /v1/* TDX 路由
│   │   ├── experimental.py   # builtin HTTP bridge
│   │   └── experimental_ws.py # builtin downstream WS
│   └── builtin_bridge/       # TDX 终端 Python 3.7 实时脚本
├── qmt/                      # QMT datasource 服务 (Port 9002)
│   ├── main.py               # FastAPI 应用入口
│   ├── routes/               # REST API 路由
│   │   ├── v1/               # native QMT /v1/bars/query
│   │   ├── bridge.py         # full-QMT HTTP polling bridge
│   │   └── realtime.py       # builtin experimental realtime gateway
│   └── builtin_bridge/       # 大 QMT 内置 Python 脚本
├── tests/                    # 测试
│   ├── conftest.py           # pytest 配置和 fixtures
│   ├── unit/                 # 单元测试
│   │   ├── test_config.py
│   │   ├── test_ws_protocol.py
│   │   ├── test_adapter_mock.py
│   │   └── test_tdx_adapter.py
│   └── integration/          # 集成测试
│       ├── test_tdx_routes.py
│       ├── test_tdx_ws.py
│       ├── test_tdx_v1.py
│       ├── test_qmt_v1.py
│       ├── test_qmt_bridge_routes.py
│       └── test_tdx_live.py  # 需要真实环境 (标记为 live)
├── scripts/                  # 本地开发与契约导出脚本
│   ├── start_all.sh          # 启动所有服务
│   ├── stop_all.sh           # 停止所有服务
│   └── health_check.sh       # 健康检查
```

## API 文档

启动服务后访问 OpenAPI 文档：
- TDX: http://localhost:9001/docs
- QMT: http://localhost:9002/docs

### 主要 API 端点

#### TDX datasource (Port 9001)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/v1/bars/query` | normalized 历史 bars |
| POST | `/v1/snapshots/query` | normalized 行情快照 |
| POST | `/v1/sectors/query` | normalized 板块成份查询 |
| POST | `/v1/sectors/list/query` | normalized 板块列表 |
| POST | `/v1/calendar/trading-dates/query` | normalized 交易日 |
| POST | `/v1/securities/query` | normalized 证券列表 |
| POST | `/v1/securities/info/query` | normalized 证券详情 |
| POST | `/v1/price-volume/query` | normalized 价量数据 |
| POST | `/v1/finance/financial-data/query` | normalized 专业财务数据 |
| POST | `/v1/finance/financial-data/by-date/query` | normalized 指定日期财务数据 |
| POST | `/v1/reference/dividend-factors/query` | normalized 除权除息 |
| POST | `/v1/reference/share-capital/query` | normalized 股本数据 |
| POST | `/v1/instruments/convertible-bonds/query` | normalized 可转债信息 |
| POST | `/v1/instruments/tracking-etfs/query` | normalized 跟踪 ETF 信息 |
| POST | `/v1/raw/tdx/call` | operator/debug only TDX raw 调用 |
| WS | `/ws/tdx-experimental/{client_id}` | TDX builtin 实时行情与订阅同步 |

`/tdx/bridge/owner`、`/tdx/bridge/poll`、`/tdx/bridge/result`、
`/tdx/bridge/snapshot`、`/tdx/bridge/evidence/{symbol}`、`/tdx/bridge/health`
和独立实时 WebSocket始终注册。bridge HTTP 路由只允许 loopback 访问；Mist backend
通过 WebSocket同步完整订阅集合，不直接访问这些 HTTP 路由。

#### QMT datasource (Port 9002)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/v1/bars/query` | QMT native 历史 bars，返回 `data.marketData` |
| POST | `/qmt/bridge/owner` | 大 QMT 内置 Python bridge 注册 owner |
| POST | `/qmt/bridge/commands` | 受控入队一条 full-QMT bridge 命令 |
| GET | `/qmt/bridge/commands/{command_id}` | 查询 bridge 命令结果或 pending 状态 |
| POST | `/qmt/bridge/poll` | 大 QMT 内置 Python bridge 拉取命令 |
| POST | `/qmt/bridge/result` | 大 QMT 内置 Python bridge 回写结果 |
| GET | `/qmt/bridge/health` | bridge owner/queue 健康状态 |

`QMT_REALTIME_MODE=builtin_experimental` 时额外启用独立实时 owner/poll/snapshot、
loopback health 和下游实验 WebSocket。大 QMT 内置脚本仍只使用标准库 HTTP polling，
不会在终端脚本中启动 WebSocket、线程或子进程。

### WebSocket 消息协议

客户端发送：
```json
// 心跳
{"type": "ping"}

// 订阅行情
{"type": "subscribe", "stocks": ["SH600519", "SZ000001"]}
```

服务端推送：
```json
// 心跳响应
{"type": "pong", "timestamp": "2024-01-01T00:00:00"}

// 订阅确认
{"type": "subscribed", "data": {"stocks": ["SH600519"]}}

// 行情数据
{"type": "quote", "data": {"code": "SH600519", "price": 1800.00}}

// 错误消息
{"type": "error", "message": "错误描述"}
```

## 代码质量

```bash
# Lint
uv run ruff check .

# Format
uv run ruff format .

# Type check (strict mode)
uv run pyright src/
```

## Windows 部署

Windows 部署由 `mist-deploy` 仓库统一管理。

### TDX WinSW 服务路径

新的 TDX 路径仍然是 `mist-datasource` 中的 Python TDX adapter，对外提供
`http://127.0.0.1:9001` 上的 FastAPI HTTP/WebSocket 接口；不是让 NestJS
直接调用通达信本地 HTTP 或 SDK。

Windows 服务名为 `mist-tdx-datasource`，由 WinSW 管理：

生产部署和 smoke 请使用 `mist-deploy` 的 `Manage Windows TDX Datasource`
workflow；本仓库不再保留旧 adapter-aware WinSW smoke。

### QMT WinSW 服务路径

QMT datasource 独立运行在 `http://127.0.0.1:9002`，Windows 服务名为
`mist-qmt-datasource`，同样由 WinSW 管理：

```powershell
.\scripts\winsw\install-qmt-datasource.ps1 -WinSWExe D:\tools\winsw\winsw.exe
.\scripts\winsw\test-qmt-datasource.ps1
```

这个服务始终负责 native `/v1/bars/query` 和 full-QMT HTTP polling bridge；
实验模式还会启用内存实时 collector 与独立下游 WebSocket。大 QMT 内置 Python
策略脚本不由 WinSW 或部署脚本加载、注册或
删除；需要时仍在大 QMT 客户端 UI 中手动处理。

迁移期间，Mist backend 的 `TDX_BASE_URL` 默认仍保持：

```env
TDX_BASE_URL=http://127.0.0.1:9001
```

这个新 TDX 路径不需要 `DATASOURCE_DB`。订阅意图、K 线持久化和业务数据仍由
NestJS / MySQL 负责，Python adapter 只维护运行时订阅、采集和转发状态。

TDX 终端登录、授权状态和通达信策略清理不属于公开服务自动化的一部分。部署或重启
前仍需要运维人员确认通达信终端已登录，并在终端中手动清理冲突策略。公共
`/health` 直接报告 TDX HTTP 与 builtin bridge 状态；详细 lease 信息也可通过
loopback-only bridge health 观测。

### OpenAPI / Swagger

TDX adapter 是 FastAPI 服务，运行后可以直接查看当前接口契约：

```text
http://127.0.0.1:9001/docs
http://127.0.0.1:9001/openapi.json
```

仓库保存 TDX 唯一运行时与 QMT 两种模式的确定性契约：

```text
docs/references/tdx-openapi-builtin-experimental.json
docs/references/qmt-openapi-off.json
docs/references/qmt-openapi-builtin-experimental.json
```

更新方式：

```bash
uv run python scripts/export_openapi.py --all
```

### 内置脚本边界

Windows datasource 不复制或加载 TDX SDK。TDX 的 `tqcenter` 仅由操作员放入并注册的
终端内置脚本使用；部署 workflow 不写入 `PYPlugins/user`。QMT 同样通过大 QMT
内置 Python bridge 与 datasource 通信。

QMT bridge 预期配置：

```env
QMT_HOST=127.0.0.1
QMT_PORT=9002
QMT_BRIDGE_GATEWAY_URL=http://127.0.0.1:9002/qmt/bridge
MIST_QMT_SPIKE_OUTPUT_PATH=F:/quant/MistAPI/datasource/logs/qmt/mist_qmt_spike_output.json
```

QMT 服务始终暴露 native `/v1/bars/query` 和 HTTP polling bridge；实验模式按门禁
额外注册 realtime routes。TDX 服务不接受 QMT provider 参数。

启用 live QMT 前必须先在 Windows 大 QMT 客户端中运行：

- `qmt/builtin_bridge/mist_qmt_spike.py`
- `qmt/builtin_bridge/mist_qmt_bridge.py`

实机结果记录到 `docs/references/bigqmt-windows-spike-evidence-template.md`。生产
bridge 脚本只允许 stdlib HTTP polling；不得在 bridge 生产脚本中使用第三方库、
监听端口、线程或子进程。

部署完成后的运行态验收由 `mist-deploy` 中独立的 datasource smoke 与 desktop
recovery workflow 执行，避免仓库内另一套脚本重新引入旧 SDK 或路由假设。

TDX `/v1` 请求固定使用 TDX schema，不接受 `provider` 字段。QMT 历史 bars
请调用 QMT 服务的 `http://127.0.0.1:9002/v1/bars/query`。

**重要提示**：重新启动 TDX 进程前，必须在通达信终端中**手动删除**已注册的策略，否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。策略标识为 `sdk_path/mist_datasource.py`。

## 许可证

BSD-3-Clause
