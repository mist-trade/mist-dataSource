<p align="right">
  <strong>中文</strong> | <a href="./README.md">English</a>
</p>

# Mist Datasource 行情数据源桥接系统

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.12-blue.svg" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/uv-Package_Manager-purple.svg" alt="uv" />
  <img src="https://img.shields.io/badge/License-BSD--3--Clause-green.svg" alt="License" />
</p>

Mist Datasource 是 Mist 系统的底层行情适配网关，基于 Python 3.12 与 FastAPI 构建。通过两个独立的容器化服务，分别封装通达信（TDX）桌面终端与原生大 QMT（ThinkTrader）终端的专有能力，对外提供标准化的 HTTP 历史 K 线查询与高性能 WebSocket 实时行情流推送。




---

## 🌟 核心特性

- **双独立微服务网关架构**：
  - **TDX Datasource（端口: 9001）**：非实时接口直连通达信官方 `:17709`，实时行情通过内置 Python Bridge 直推 Snapshot。
  - **QMT Datasource（端口: 9002）**：通过内置 Python 桥接驱动原生 `subscribe_quote` / `get_market_data_ex` 接口，输出原生数据。
- **Schema-V2 Native Map Frame 实时推送**：严格规范化的实时 WebSocket 数据帧格式，实现极低延迟与零数据拷贝开销。
- **声明式订阅控制四方法**：标准化支持 `syncSubscriptions`（全量对齐）、`subscribe`（增量）、`unsubscribe`（退订）、`getSubscriptions`（查询）。
- **QMT 订阅状态 Journal 持久化**：持久化记录订阅集指纹（`subscription-journal.jsonl`），支持进程重启与网络抖动后的毫秒级无损恢复。
- **无状态容器化安全运行**：容器内以非 root 用户、只读根文件系统运行，仅对本地回环（Loopback）开放管理端点。

---

## 🔄 拓扑与数据链路

```text
┌─────────────────────────────────────────────────────────────┐
│                 Windows 宿主交互桌面会话                    │
│                                                             │
│   [TDX Desktop 终端]              [原生大 QMT 终端]         │
│           │                               │                 │
│   (PYPlugins/user Bridge)         (内置 Python Bridge)       │
│           │ TCP 直推                      │ TCP 直推 / Poll  │
└───────────┼───────────────────────────────┼─────────────────┘
            │                               │
┌───────────▼───────────────────────────────▼─────────────────┐
│               Docker Compose Appliance                      │
│                                                             │
│   ┌─────────────────────────┐   ┌─────────────────────────┐ │
│   │ tdx-datasource (:9001)  │   │ qmt-datasource (:9002)  │ │
│   │   - GET /health         │   │   - GET /health         │ │
│   │   - POST /v1/bars/query │   │   - POST /v1/bars/query │ │
│   │   - WS /ws/realtime/tdx │   │   - WS /ws/realtime/qmt │ │
│   └────────────┬────────────┘   └────────────┬────────────┘ │
└────────────────┼─────────────────────────────┼──────────────┘
                 │                             │
                 └──────────────┬──────────────┘
                                │ schema-v2 WebSocket
                                ▼
                   mist-backend Ingress (:8001)
```

---

## 📋 环境要求与 Python 兼容性

| 运行环境 | Python 版本要求 | 依赖说明 |
| :--- | :--- | :--- |
| **Datasource 容器** | `Python 3.12` | FastAPI, Pydantic v2, Uvicorn, WebSockets |
| **TDX Builtin Bridge** | `Python 3.7+` 语法 | 宿主实机 Python 3.12 + 官方 `tqcenter` |
| **QMT Builtin Bridge** | `Python 3.6` 语法 | 严格限制标准库 HTTP Polling，禁止 Python 3.7+ 特性语法 |

---

## 🚀 快速开始 (本地开发)

仓库使用 `uv` 进行现代化的 Python 依赖管理：

### 1. 同步虚拟环境

```bash
uv sync --frozen --python 3.12
```

### 2. 启动本地调试服务

```bash
# 启动 TDX Datasource 服务 (端口: 9001)
uv run uvicorn tdx.main:app --port 9001 --reload

# 启动 QMT Datasource 服务 (端口: 9002)
uv run uvicorn qmt.main:app --port 9002 --reload
```

---

## 🔌 核心接口与端点

### 1. 通达信 (TDX) 网关 — `:9001`
- `GET /health`：网关与 Bridge 健康状态。
- `POST /v1/bars/query`：历史 K 线数据查询（标准化 Rows 输出）。
- `POST /v1/finance/financial-data/query`：财务数据查询。
- `POST /v1/instruments/convertible-bonds/query`：转债数据查询。
- `WS /ws/realtime/tdx/{client_id}`：实时 Snapshot 数据流订阅。

### 2. 大 QMT 网关 — `:9002`
- `GET /health`：网关与 Bridge 健康状态。
- `POST /v1/bars/query`：原生历史 K 线查询（返回 native `data.marketData`）。
- `POST /qmt/bridge/subscriptions/*`：四方法订阅控制指令。
- `WS /ws/realtime/qmt/{client_id}`：实时行情原生数据流订阅。

---

## 🧪 测试与质量门禁

```bash
# 运行 Pytest 单元测试
uv run pytest

# 代码静态检查与规范
uv run ruff check .
uv run pyright

# 导出确定性 OpenAPI 规范文档
uv run python scripts/export_openapi.py --all
```

---

## 🚢 生产镜像与运维

同一个不可变 Docker 镜像用于启动两个独立微服务：

```bash
# 生产镜像构建
docker build -t ghcr.io/mist-trade/mist-datasource:<tag> .

# 宿主机运维重启
powershell -File scripts/manage-datasource-containers.ps1 -Source tdx -Action restart
powershell -File scripts/manage-datasource-containers.ps1 -Source qmt -Action restart
```

- TDX Bridge 运维指引：请参阅 [`tdx/builtin_bridge/README.md`](./tdx/builtin_bridge/README.md)。
- QMT Bridge 运维指引：请参阅 [`qmt/builtin_bridge/README.md`](./qmt/builtin_bridge/README.md)。

---

## 📄 许可证

本项目遵循 [BSD-3-Clause](https://opensource.org/licenses/BSD-3-Clause) 开源许可证。
