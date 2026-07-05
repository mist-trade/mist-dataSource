# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mist-datasource** is a data source bridge layer that wraps Windows-only market data providers (通达信/TDX via `tqcenter`, full QMT via built-in Python bridge) as HTTP/WebSocket services for the NestJS backend. Not a general-purpose microservice — a focused adapter layer.

## Development Commands

```bash
uv sync                                    # Install dependencies
uv run pytest                              # Run all tests
uv run pytest -m "not live"                # Skip Windows-only tests
uv run pytest tests/integration/test_tdx_routes.py::test_name  # Single test
uv run pytest --cov=src --cov=tdx --cov=qmt  # With coverage
uv run ruff check .                        # Lint
uv run ruff format .                       # Format
uv run pyright src/                        # Type check (strict mode)

# Start instances (macOS uses mock adapters automatically)
uv run uvicorn tdx.main:app --port 9001 --reload
uv run uvicorn qmt.main:app --port 9002 --reload
```

## Architecture

### Multi-Instance Pattern

Each instance is a separate FastAPI app. Shared code lives in `src/`.

| Instance | Port | Adapter | SDK | Stock Code Format |
|----------|------|---------|-----|-------------------|
| tdx | 9001 | `TdxLegacyAdapter`/`TdxLegacyMockAdapter` | `tqcenter.tq` | `SH600519`, `SZ000001` |
| qmt | 9002 | native v1 + command gateway | full-QMT built-in Python HTTP polling bridge | `600000.SH`, `000001.SZ` |

### Request Flow

```text
NestJS backend → TDX HTTP /v1 or legacy /api/tdx/* → TDX routes/provider/adapter
NestJS backend → TDX WebSocket /ws/quote/{client_id} → subscription/collector
NestJS backend → QMT HTTP /v1/bars/query → QMT native local-DAT provider
Full-QMT script → QMT HTTP polling bridge /qmt/bridge/{commands,owner,poll,result,health}
```

### Runtime State

Each `main.py` owns the process runtime objects. TDX owns `tdx_provider`,
`tdx_legacy_adapter`, `tdx_legacy_bridge`, `tdx_legacy_collector`,
`tdx_legacy_subscription_client`, and `ws_manager`; QMT owns
`qmt_provider` and `qmt_command_gateway`. FastAPI lifespan startup mirrors
these objects onto `app.state`, and routes read runtime dependencies from
`request.app.state` or `websocket.app.state`:

```python
def get_tdx_legacy_adapter(request: Request):
    return request.app.state.tdx_legacy_adapter
```

Routes do not import process globals from `tdx.main` or `qmt.main`; use the
shared route dependency helpers and `app.state` instead.

### Adapter Pattern (`src/adapter_legacy/`)

`base.py` defines `TdxLegacyAdapterBase`, which only defines the lifecycle abstract
methods:

- `initialize()` - Initialize SDK connection
- `shutdown()` - Close SDK connection

Provider-specific methods live on the `TdxLegacyAdapterProtocol` Protocol and concrete
TDX adapter. QMT does not use the adapter factory path; QMT history bars live in
`src/datasource/qmt`, and live/native command execution goes through the HTTP
polling bridge.

`src/adapter_legacy/__init__.py` exposes `create_tdx_legacy_adapter` only. Do not reintroduce
a QMT local SDK adapter or mock adapter.

### API Routes

| Instance | Route Group | Endpoints |
|----------|-------------|-----------|
| TDX | `/v1/bars/query` | normalized historical bars |
| TDX | `/v1/snapshots/query` | normalized market snapshots |
| TDX | `/v1/sectors/query` | normalized sector members |
| TDX | `/v1/sectors/list/query` | normalized sector lists |
| TDX | `/v1/calendar/trading-dates/query` | normalized trading calendar |
| TDX | `/v1/securities/query` | normalized securities |
| TDX | `/v1/securities/info/query` | normalized security info |
| TDX | `/v1/price-volume/query` | normalized price/volume data |
| TDX | `/v1/finance/financial-data/query` | normalized financial data |
| TDX | `/v1/finance/financial-data/by-date/query` | normalized financial data by date |
| TDX | `/v1/reference/relations/query` | normalized relations data |
| TDX | `/v1/reference/ipo/query` | normalized IPO data |
| TDX | `/v1/reference/share-capital/query` | normalized share-capital data |
| TDX | `/v1/reference/dividend-factors/query` | normalized dividend factors |
| TDX | `/v1/reports/stock-trade/query` | normalized stock trade report aggregate |
| TDX | `/v1/reports/sector-trade/query` | normalized sector trade report aggregate |
| TDX | `/v1/reports/market-trade/query` | normalized market trade report aggregate |
| TDX | `/v1/instruments/convertible-bonds/query` | normalized convertible bond metadata |
| TDX | `/v1/instruments/tracking-etfs/query` | normalized tracking ETF metadata |
| TDX | `/v1/formulas/*` | normalized formula metadata/data/execution |
| TDX | `/v1/raw/tdx/call` | operator/debug raw TDX escape hatch |
| QMT | `/v1/bars/query` | native historical bars as `data.marketData` |
| QMT | `/qmt/bridge/{commands,owner,poll,result,health}` | full-QMT built-in Python HTTP polling bridge |
| Both | `/health` | Health check |
| TDX | `/ws/quote/{client_id}` | Real-time quotes |

TDX legacy `/api/tdx/*` routes remain registered for deprecated compatibility
only; new product paths should use `/v1/*`.

### WebSocket Protocol

Messages use `WSMessage` pydantic model (`src/ws/protocol.py`): `{type, data, timestamp}`. Client sends `{type: "ping"}` for heartbeat, `{type: "subscribe", stocks: [...]}` to subscribe. Server responds with `pong`, `subscribed`, `quote`, or `error`. Connection manager (`src/ws/manager.py`) handles 1-2 NestJS backend connections.

### Directory Layout

```
src/core/          config.py (pydantic-settings), exceptions.py, logging.py
src/adapter_legacy/       base.py (lifecycle ABC + TDX Protocol), factory in __init__.py, tdx/, mock/
src/ws/            protocol.py (WSMessage), manager.py (ConnectionManager)
tdx/               main.py, routes/dependencies.py, routes/{legacy,v1}/
qmt/               main.py, config.py, routes/{bridge,v1}.py, builtin_bridge/
tests/             conftest.py (httpx ASGI fixtures), unit/, integration/
```

## Key Conventions

- **Config**: `src/core/config.py` — single `settings = AppSettings()` singleton. `APP_ENV=development` selects the TDX mock adapter; QMT local DAT is controlled by `QMT_LOCAL_DAT_*`.
- **Tests**: `pytest-asyncio` with `asyncio_mode = "auto"` (configured in pyproject.toml). Fixtures in `conftest.py` provide `tdx_client` / `qmt_client` as httpx `AsyncClient` with ASGI transport.
- **Code style**: ruff (line length 100, Python 3.12 target), pyright strict mode, pre-commit hooks.
- **SDK references**: Use `docs/references/*` for datasource coverage, design decisions, and smoke references. If a provider API shape is missing there, fetch current official docs and update `docs/references/*` instead of relying on stale root-level snapshots.
- **Cross-platform**: macOS development uses the TDX mock adapter. Windows production requires TDX terminal for TDX and a separately validated full-QMT HTTP polling bridge plus configured local DAT directory for QMT history bars.
- **TDX 策略管理**: 通达信终端用文件路径作为策略名标识。重新启动 TDX 进程前必须在通达信终端中**手动删除**已注册的策略, 否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。策略标识为 `sdk_path/mist_datasource.py`。
- **Windows 部署**: 使用 `scripts/deploy_windows.ps1` 安装依赖并做临时启动验证 (需管理员权限)。支持 `-Only install|test` 运行单步。
