<p align="right">
  <a href="./README.zh-CN.md">中文</a> | <strong>English</strong>
</p>

# Mist Datasource — TDX/QMT Market Data Gateway

<p align="left">
  <img src="https://img.shields.io/badge/Python-3.12-blue.svg" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688.svg" alt="FastAPI" />
  <img src="https://img.shields.io/badge/uv-Package_Manager-purple.svg" alt="uv" />
  <img src="https://img.shields.io/badge/License-BSD--3--Clause-green.svg" alt="License" />
</p>

Low-level market-data gateway for Mist, built on Python 3.12 & FastAPI. Two containerized services wrap the TDX and native QMT desktop terminals, exposing unified HTTP historical K-line queries and high-performance WebSocket realtime streaming.

> See [README.zh-CN.md](./README.zh-CN.md) for Chinese.

---

## 🌟 Core Features

- **Dual microservice gateway**:
  - **TDX Datasource (:9001)**: non-realtime queries hit the official TDX `:17709` directly; realtime snapshots are pushed via the built-in Python Bridge.
  - **QMT Datasource (:9002)**: drives native `subscribe_quote` / `get_market_data_ex` via the built-in Python bridge and emits raw data.
- **Schema-V2 Native Map Frame realtime push**: strictly normalized WebSocket frame format for ultra-low latency and zero-copy overhead.
- **Declarative 4-method subscription control**: `syncSubscriptions` (full alignment), `subscribe` (incremental), `unsubscribe` (remove), `getSubscriptions` (query).
- **QMT subscription journal persistence**: fingerprints the subscription set to `subscription-journal.jsonl` for lossless recovery across restarts & network blips.
- **Stateless hardened containers**: runs as non-root with a read-only root filesystem, management endpoints only on loopback.

---

## 🔄 Topology & Data Path

```text
┌─────────────────────────────────────────────────────────────┐
│                 Windows Host — Interactive Session          │
│                                                             │
│   [TDX Desktop Terminal]          [Native QMT Terminal]     │
│           │                               │                 │
│   (PYPlugins/user Bridge)         (Built-in Python Bridge)  │
│           │ TCP push                      │ TCP push / Poll │
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

## 📋 Requirements & Python Compatibility

| Runtime | Python Version | Notes |
| :--- | :--- | :--- |
| **Datasource Container** | `Python 3.12` | FastAPI, Pydantic v2, Uvicorn, WebSockets |
| **TDX Builtin Bridge** | `Python 3.7+` syntax | Host Python 3.12 + official `tqcenter` |
| **QMT Builtin Bridge** | `Python 3.6` syntax | Stdlib-only HTTP polling, no Python 3.7+ syntax |

---

## 🚀 Quick Start (Local Dev)

Uses `uv` for modern Python dependency management:

### 1. Sync virtual environment

```bash
uv sync --frozen --python 3.12
```

### 2. Start local debug services

```bash
# TDX Datasource (:9001)
uv run uvicorn tdx.main:app --port 9001 --reload

# QMT Datasource (:9002)
uv run uvicorn qmt.main:app --port 9002 --reload
```

---

## 🔌 Core Endpoints

### 1. TDX Gateway — `:9001`
- `GET /health`: gateway & Bridge health.
- `POST /v1/bars/query`: historical K-line query (normalized Rows output).
- `POST /v1/finance/financial-data/query`: financial data query.
- `POST /v1/instruments/convertible-bonds/query`: convertible bond query.
- `WS /ws/realtime/tdx/{client_id}`: realtime Snapshot stream.

### 2. QMT Gateway — `:9002`
- `GET /health`: gateway & Bridge health.
- `POST /v1/bars/query`: native historical K-line query (returns `data.marketData`).
- `POST /qmt/bridge/subscriptions/*`: 4-method subscription control.
- `WS /ws/realtime/qmt/{client_id}`: realtime native stream.

---

## 🧪 Testing & Quality Gates

```bash
# Pytest unit tests
uv run pytest

# Lint & typecheck
uv run ruff check .
uv run pyright

# Export deterministic OpenAPI docs
uv run python scripts/export_openapi.py --all
```

---

## 🚢 Production Image & Ops

One immutable Docker image runs two microservices:

```bash
# Production image build
docker build -t ghcr.io/mist-trade/mist-datasource:<tag> .

# Host ops restart
powershell -File scripts/manage-datasource-containers.ps1 -Source tdx -Action restart
powershell -File scripts/manage-datasource-containers.ps1 -Source qmt -Action restart
```

- TDX Bridge ops: [`tdx/builtin_bridge/README.md`](./tdx/builtin_bridge/README.md)
- QMT Bridge ops: [`qmt/builtin_bridge/README.md`](./qmt/builtin_bridge/README.md)

---

## 📄 License

Licensed under [BSD-3-Clause](https://opensource.org/licenses/BSD-3-Clause).
