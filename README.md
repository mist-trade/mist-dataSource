# Mist-Datasource

数据源桥接层 - 将通达信 (TDX) 与大 QMT 内置 Python 数据能力包装为 HTTP/WebSocket 服务。

## 项目定位

mist-datasource 是 NestJS 后端的**数据源桥接层**，核心职责：

- 将通达信 (TDX) 与大 QMT 内置 Python 数据能力包装为 HTTP/WebSocket 服务
- 通过 WebSocket 将实时行情推送到 NestJS 后端
- 提供统一的适配器层抽象，屏蔽底层 SDK 差异

**不是**一个通用的 WebSocket 微服务平台，而是一个**适配器层 (Adapter Layer)**。

## 架构总览

```
通达信终端 (Windows)          大 QMT 客户端 (Windows)
      │                              │
      │ tqcenter SDK                 │ 内置 Python bridge
      ▼                              ▼
┌─────────────┐              ┌─────────────┐
│  Instance 1 │              │  Instance 2 │
│  TDX Adapter│              │  QMT Adapter│
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
| Python | 3.12+ | datasource 服务使用 3.12；TDX/QMT 客户端内置 Python 版本以 Windows 实机为准 |
| 包管理 | uv | 速度快，lockfile 可靠 |
| 框架 | FastAPI | 异步支持好，自动 OpenAPI 文档 |
| 配置 | pydantic-settings | 类型安全的环境变量管理 |
| 代码质量 | ruff + pyright + pre-commit | 统一工具链 |
| 测试 | pytest + pytest-asyncio + httpx | 异步测试支持，ASGI transport |

## 端口规划

| Instance | 端口 | 用途 |
|----------|------|------|
| tdx | 9001 | TDX 适配器 |
| qmt | 9002 | QMT 适配器 |

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
- TDX/QMT 适配器自动切换为 Mock 模式（`APP_ENV=development`）
- Mock 返回随机数据，WebSocket 定期推送模拟行情
- 可以正常开发/测试 REST API 和 WebSocket 推送逻辑

### Windows 生产
- `APP_ENV=production`，TDX 使用真实 SDK；QMT 需要大 QMT 内置 bridge 完成 Windows spike 后启用
- 前置条件：通达信终端已启动；大 QMT bridge 需要单独执行 spike 和策略脚本
- 使用 `scripts/deploy_windows.ps1` 安装依赖并做临时启动验证

## 目录结构

```
mist-datasource/
├── docs/references/          # TDX/QMT datasource 设计、覆盖矩阵和 smoke 参考
├── src/                      # 共享核心代码
│   ├── core/                 # 配置、日志、异常
│   │   ├── config.py         # pydantic-settings 配置
│   │   ├── logging.py        # 日志配置
│   │   └── exceptions.py     # 自定义异常
│   ├── adapter/              # 适配器层
│   │   ├── base.py           # MarketDataAdapter 抽象基类
│   │   ├── tdx/              # TDX 真实适配器
│   │   ├── qmt/              # QMT 真实适配器
│   │   └── mock/             # Mock 适配器 (开发用)
│   └── ws/                   # WebSocket 管理
│       ├── protocol.py       # WSMessage 消息协议
│       └── manager.py        # ConnectionManager 连接管理
├── tdx/                      # TDX 适配器服务 (Port 9001)
│   ├── main.py               # FastAPI 应用入口
│   ├── config.py             # TDX 特定配置
│   ├── routes/               # REST API 路由
│   │   ├── market.py         # 行情数据
│   │   ├── stock.py          # 股票信息
│   │   ├── financial.py      # 财务数据
│   │   ├── value.py          # 估值数据
│   │   ├── sector.py         # 板块数据
│   │   ├── etf.py            # ETF 数据
│   │   ├── client.py         # 客户端管理
│   │   └── ws.py             # WebSocket 路由
│   └── services/             # 业务逻辑层
│       └── tdx_service.py    # TDX 服务
├── qmt/                      # QMT 适配器服务 (Port 9002)
│   ├── main.py               # FastAPI 应用入口
│   ├── config.py             # QMT 特定配置
│   ├── routes/               # REST API 路由
│   │   ├── market.py         # 行情数据
│   │   └── ws.py             # WebSocket 路由
│   └── services/             # 业务逻辑层
│       └── qmt_service.py    # QMT 服务
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
│       ├── test_tdx_service.py
│       ├── test_qmt_service.py
│       └── test_tdx_live.py  # 需要真实环境 (标记为 live)
├── scripts/                  # 脚本
│   ├── start_all.sh          # 启动所有服务
│   ├── stop_all.sh           # 停止所有服务
│   ├── health_check.sh       # 健康检查
│   ├── deploy_windows.ps1    # Windows 部署脚本
│   └── run_live_tests.ps1    # 运行真实环境测试
```

## API 文档

启动服务后访问 OpenAPI 文档：
- TDX: http://localhost:9001/docs
- QMT: http://localhost:9002/docs

### 主要 API 端点

#### TDX 适配器 (Port 9001)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/tdx/stock-list-in-sector` | 获取板块股票列表 |
| GET | `/api/tdx/market-data` | 获取历史行情数据 |
| GET | `/api/tdx/market-snapshot` | 获取实时行情快照 |
| GET | `/api/tdx/trading-dates` | 获取交易日列表 |
| GET | `/api/tdx/divid-factors` | 获取除权除息数据 |
| GET | `/api/tdx/gb-info` | 获取股本数据 |
| POST | `/api/tdx/refresh-cache` | 刷新行情缓存 |
| POST | `/api/tdx/refresh-kline` | 刷新 K 线缓存 |
| POST | `/api/tdx/download-file` | 下载特定数据文件 |
| GET | `/api/tdx/instrument-detail` | 获取合约详情 |
| GET | `/api/tdx/full-tick` | 获取完整tick数据 |
| GET | `/api/tdx/financial` | 获取财务数据 |
| GET | `/api/tdx/index-weight` | 获取指数权重 |
| GET | `/api/tdx/sector-list` | 获取板块列表 |
| GET | `/api/tdx/kzz-info` | 获取可转债信息 |
| WS | `/ws/quote/{client_id}` | 实时行情订阅 |

#### QMT 适配器 (Port 9002)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/api/qmt/stocks` | 获取股票列表 |
| GET | `/api/qmt/market-data` | 获取历史行情数据 |
| WS | `/ws/quote/{client_id}` | 实时行情订阅 |

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

使用 PowerShell 脚本一键部署（需要管理员权限）：

### TDX WinSW 服务路径

新的 TDX 路径仍然是 `mist-datasource` 中的 Python TDX adapter，对外提供
`http://127.0.0.1:9001` 上的 FastAPI HTTP/WebSocket 接口；不是让 NestJS
直接调用通达信本地 HTTP 或 SDK。

Windows 服务名为 `mist-tdx-datasource`，由 WinSW 管理：

```powershell
.\scripts\winsw\install-tdx-datasource.ps1 -WinSWExe D:\tools\winsw\winsw.exe
.\scripts\winsw\test-tdx-datasource.ps1
```

迁移期间，Mist backend 的 `TDX_BASE_URL` 默认仍保持：

```env
TDX_BASE_URL=http://127.0.0.1:9001
```

这个新 TDX 路径不需要 `DATASOURCE_DB`。订阅意图、K 线持久化和业务数据仍由
NestJS / MySQL 负责，Python adapter 只维护运行时订阅、采集和转发状态。

TDX 终端登录、授权状态和通达信策略清理不属于公开服务自动化的一部分。部署或重启
前仍需要运维人员确认通达信终端已登录，并在终端中手动清理冲突策略；服务只通过
`/health` 暴露 `tdxHttpReachable`、`tqInitialized`、`collectorState` 等状态，供
私有 guard 或人工运维判断。

### OpenAPI / Swagger

TDX adapter 是 FastAPI 服务，运行后可以直接查看当前接口契约：

```text
http://127.0.0.1:9001/docs
http://127.0.0.1:9001/openapi.json
```

仓库里也保存了一份从当前 `tdx.main:app.openapi()` 导出的契约：

```text
docs/references/tdx-openapi.json
docs/references/tdx-openapi-summary.md
```

更新方式：

```bash
uv run python scripts/export_openapi.py
```

### SDK 路径约束

Windows 生产部署不会复制或打包通达信 SDK 文件。QMT 生产接入不再走本地 SDK 目录，而是通过大 QMT 内置 Python bridge 与 datasource 通信。

TDX 预期目录结构：

```text
F:/quant/tdx/PYPlugins/
├── TPythClient.dll
├── tpythclient.py        # 如果你的通达信安装提供这个文件，通常在这里
└── user/
    └── tqcenter.py
```

`TDX_SDK_PATH` 必须指向包含 `tqcenter.py` 的 `user` 目录：

```env
TDX_SDK_PATH=F:/quant/tdx/PYPlugins/user
```

不要只复制 `tqcenter.py` 到部署包。`TPythClient.dll` 在 `TDX_SDK_PATH` 的上一级目录，SDK 会按这个父目录关系定位它；移动目录后需要同步修改 `.env`，并可能需要在通达信终端里清理旧策略身份。

QMT bridge 预期配置，保留给 Windows full-QMT spike 和后续启用：

```env
QMT_HOST=127.0.0.1
QMT_PORT=9002
QMT_BRIDGE_GATEWAY_URL=http://127.0.0.1:9012/qmt/bridge
```

当前 Mist Windows appliance 不注册也不启动 live QMT provider。保留这些配置不会影响 TDX/Backend 的 WinSW 部署。

启用 live QMT 前必须先在 Windows 大 QMT 客户端中运行：

- `qmt/builtin_bridge/mist_qmt_spike.py`
- `qmt/builtin_bridge/mist_qmt_bridge.py`

实机结果记录到 `docs/references/bigqmt-windows-spike-evidence-template.md`。如果
第三方库、WebSocket、监听端口、线程或子进程没有通过 spike，不得在 bridge
生产脚本中使用这些能力。

部署前可先运行 SDK 预检：

```powershell
.\scripts\preflight-sdk.ps1
```

`deploy_windows.ps1` 只负责依赖安装和临时启动验证；Mist Windows appliance
不再依赖 NSSM，也不会通过 datasource 仓库注册 QMT 服务。

```powershell
# 完整验证（安装依赖 + 运行测试）
.\scripts\deploy_windows.ps1

# 仅安装
.\scripts\deploy_windows.ps1 -Only install

# 仅运行测试
.\scripts\deploy_windows.ps1 -Only test
```

部署完成并启动 WinSW 服务后，用运行态总入口做一次完整验收：

```powershell
.\scripts\run-runtime-checks.ps1 -ApplianceRoot F:\quant\MistAPI

# 交易时间强制等待实时 quote；这会改 TDX 订阅，只在 backend 未占用 leader 时使用
.\scripts\run-runtime-checks.ps1 -ApplianceRoot F:\quant\MistAPI -RequireLiveQuote -AllowWebSocketSubscriptionChange

# 加测 Phase 3 财务/报告链路；默认用 get_gp_one_data，适合非交易时段
.\scripts\run-runtime-checks.ps1 -ApplianceRoot F:\quant\MistAPI -IncludeFinanceReportSmoke

# 加测 Phase 2/4 深烟测；默认不跑，适合人工真机验证时开启
.\scripts\run-runtime-checks.ps1 -ApplianceRoot F:\quant\MistAPI -IncludeReferenceInstrumentSmoke -IncludeFormulaSmoke

# 需要从 datasource 侧重跑安装/临时启动验证时显式开启
.\scripts\run-runtime-checks.ps1 -RunDatasourceInstall -RunDatasourceStartupTest
```

运行态总入口会检查 datasource health、provider manifest、TDX native HTTP
shape、normalized bars/snapshots/sectors、Phase 1 calendar/security/sector-list/
price-volume endpoints、WebSocket ping/pong，以及 appliance health。通过
`-IncludeFinanceReportSmoke` 可额外检查 Phase 3 finance/report 的 native
`get_gp_one_data` 与 normalized `/v1/finance/single-data/query`；
`-IncludeReferenceInstrumentSmoke` 与 `-IncludeFormulaSmoke` 可额外检查
Phase 2 reference/instrument 和 Phase 4 formula 的 read-only 路径。

`/v1` normalized 请求默认使用 `provider=tdx`。如果显式传
`provider=qmt`，当前会返回 `PROVIDER_CAPABILITY_UNSUPPORTED`，用于固定
QMT 后续接入时的错误契约；Mist Windows appliance 目前仍不启动 QMT 服务。

**重要提示**：重新启动 TDX 进程前，必须在通达信终端中**手动删除**已注册的策略，否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。策略标识为 `sdk_path/mist_datasource.py`。

## 许可证

BSD-3-Clause
