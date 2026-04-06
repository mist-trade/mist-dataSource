# Mist-Datasource

数据源桥接层 - 将通达信 (TDX) 和 miniQMT 的本地 SDK 接口包装为 HTTP/WebSocket 服务。

## 项目定位

mist-datasource 是 NestJS 后端的**数据源桥接层**，核心职责：

- 将通达信 (TDX) 和 miniQMT 的本地 SDK 接口包装为 HTTP/WebSocket 服务
- 通过 WebSocket 将实时行情推送到 NestJS 后端
- 提供统一的适配器层抽象，屏蔽底层 SDK 差异

**不是**一个通用的 WebSocket 微服务平台，而是一个**适配器层 (Adapter Layer)**。

## 架构总览

```
通达信终端 (Windows)          miniQMT 客户端 (Windows)
      │                              │
      │ tqcenter SDK                 │ xtquant SDK
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
| Python | 3.12+ | xtquant 最高支持 3.12；tqcenter 支持 3.7-3.14 |
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
| aktools | 8080 | AKTools (待迁移) |

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
- `APP_ENV=production`，使用真实 SDK
- 前置条件：通达信终端 / MiniQMT 客户端已启动
- 使用 `scripts/deploy_windows.ps1` 一键部署为 Windows 服务

## 目录结构

```
mist-datasource/
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
└── docs/                     # 文档
    ├── TDX.md                # TDX SDK API 文档
    └── QMT.md                # QMT SDK API 文档
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

```powershell
# 完整部署（安装依赖 + 运行测试 + 注册服务）
.\scripts\deploy_windows.ps1

# 仅安装
.\scripts\deploy_windows.ps1 -Only install

# 仅运行测试
.\scripts\deploy_windows.ps1 -Only test

# 仅注册服务
.\scripts\deploy_windows.ps1 -Only service

# 跳过服务注册
.\scripts\deploy_windows.ps1 -SkipService
```

**重要提示**：在服务重启前，必须在通达信终端中**手动删除**已注册的策略，否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。服务注册身份为 `sdk_path/mist_datasource.py`。

## 许可证

BSD-3-Clause
