# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mist-datasource** is a data source bridge layer that wraps Windows-only trading SDKs (通达信/TDX via `tqcenter`, miniQMT via `xtquant`) as HTTP/WebSocket services for the NestJS backend. Not a general-purpose microservice — a focused adapter layer.

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
| tdx | 9001 | `TDXAdapter`/`TDXMockAdapter` | `tqcenter.tq` | `SH600519`, `SZ000001` |
| qmt | 9002 | `QMTAdapter`/`QMTMockAdapter` | `xtquant.xtdata` | `600000.SH`, `000001.SZ` |

### Request Flow

```
NestJS backend → HTTP /api/{tdx|qmt}/* → routes/ → adapter/provider from app.state
                → WebSocket /ws/quote/{client_id} → ws_manager.broadcast()
```

### Runtime State

Each `main.py` owns the process runtime objects: `{tdx|qmt}_adapter` (adapter instance), TDX provider/collector/subscription objects, and `ws_manager` (WebSocket connection manager). FastAPI lifespan startup mirrors these objects onto `app.state`, and routes read runtime dependencies from `request.app.state` or `websocket.app.state`:

```python
def _get_adapter(request: Request):
    return request.app.state.tdx_adapter
```

Routes do not import process globals from `tdx.main` or `qmt.main`; use the
shared route dependency helpers and `app.state` instead.

### Adapter Pattern (`src/adapter/`)

`base.py` defines `MarketDataAdapter`, which only defines the lifecycle abstract
methods:

- `initialize()` - Initialize SDK connection
- `shutdown()` - Close SDK connection

Provider-specific methods live on narrower Protocols in `src/adapter/base.py`
(`TdxDataAdapter`, `QmtDataAdapter`) and on the concrete TDX/QMT adapters. Do
not add a giant shared ABC for provider APIs with different native signatures;
keep normalized HTTP contracts in the route/provider layer and provider quirks
inside each adapter.

Factory functions in `__init__.py` (`create_tdx_adapter`, `create_qmt_adapter`) return real or mock adapters based on `settings.is_production` (controlled by `APP_ENV` env var).

### API Routes

| Instance | Route Group | Endpoints |
|----------|-------------|-----------|
| TDX | `/api/tdx/market` | stock-list-in-sector, market-data, market-snapshot, trading-dates, divid-factors, gb-info, refresh-cache, refresh-kline, download-file |
| TDX | `/api/tdx/stock` | instrument-detail, stock-info, report-data, more-info, relation |
| TDX | `/api/tdx/financial` | financial-data, download-financial-data, financial-data-by-date |
| TDX | `/api/tdx/value` | bkjy-value, gpjy-value, scjy-value (by-date variants) |
| TDX | `/api/tdx/sector` | sector-list, download-sector-data, index-weight, download-index-weight, user-sector CRUD |
| TDX | `/api/tdx/etf` | kzz-info, ipo-info, trackzs-etf-info |
| TDX | `/api/tdx/client` | exec-to-tdx, send-message, print-to-tdx |
| QMT | `/api/qmt/market` | stocks, market-data |
| Both | `/health` | Health check |
| Both | `/ws/quote/{client_id}` | Real-time quotes |

### WebSocket Protocol

Messages use `WSMessage` pydantic model (`src/ws/protocol.py`): `{type, data, timestamp}`. Client sends `{type: "ping"}` for heartbeat, `{type: "subscribe", stocks: [...]}` to subscribe. Server responds with `pong`, `subscribed`, `quote`, or `error`. Connection manager (`src/ws/manager.py`) handles 1-2 NestJS backend connections.

### Directory Layout

```
src/core/          config.py (pydantic-settings), exceptions.py, logging.py
src/adapter/       base.py (lifecycle ABC + provider Protocols), factory in __init__.py, tdx/, qmt/, mock/
src/ws/            protocol.py (WSMessage), manager.py (ConnectionManager)
tdx/               main.py, config.py, routes/{dependencies,legacy,v1,ws}.py
qmt/               main.py, config.py, routes/{dependencies,market,ws}.py
tests/             conftest.py (httpx ASGI fixtures that auto-init adapters), unit/, integration/
```

## Key Conventions

- **Config**: `src/core/config.py` — single `settings = AppSettings()` singleton. `APP_ENV=development` selects mock adapters, `production` selects real SDKs.
- **Tests**: `pytest-asyncio` with `asyncio_mode = "auto"` (configured in pyproject.toml). Fixtures in `conftest.py` provide `tdx_client` / `qmt_client` as httpx `AsyncClient` with ASGI transport. These fixtures automatically initialize the adapter before yielding and shut it down in cleanup.
- **Code style**: ruff (line length 100, Python 3.12 target), pyright strict mode, pre-commit hooks.
- **SDK references**: Use `docs/references/*` for datasource coverage, design decisions, and smoke references. If a provider API shape is missing there, fetch current official docs and update `docs/references/*` instead of relying on stale root-level snapshots.
- **Cross-platform**: macOS development uses mock adapters returning random data. Windows production requires TDX terminal or MiniQMT client running.
- **TDX 策略管理**: 通达信终端用文件路径作为策略名标识。重新启动 TDX 进程前必须在通达信终端中**手动删除**已注册的策略, 否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。策略标识为 `sdk_path/mist_datasource.py`。
- **Windows 部署**: 使用 `scripts/deploy_windows.ps1` 安装依赖并做临时启动验证 (需管理员权限)。支持 `-Only install|test` 运行单步。
