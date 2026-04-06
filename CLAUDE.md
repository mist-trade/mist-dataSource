# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**mist-datasource** is a data source bridge layer that wraps Windows-only trading SDKs (通达信/TDX via `tqcenter`, miniQMT via `xtquant`) as HTTP/WebSocket services for the NestJS backend. Not a general-purpose microservice — a focused adapter layer.

## Development Commands

```bash
uv sync                                    # Install dependencies
uv run pytest                              # Run all tests
uv run pytest tests/integration/test_tdx_service.py::test_name  # Single test
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
NestJS backend → HTTP /api/{tdx|qmt}/* → routes/ → adapter (module global in main.py)
                → WebSocket /ws/quote/{client_id} → ws_manager.broadcast()
```

### Module-Level Singletons

Each `main.py` holds module-level globals: `{tdx|qmt}_adapter` (adapter instance) and `ws_manager` (WebSocket connection manager). Routes and services import these directly from `main.py`. Services use singleton pattern (e.g., `tdx_service = TDXService()` in `tdx/services/`).

### Adapter Pattern (`src/adapter/`)

`base.py` defines `MarketDataAdapter` with:
- **4 abstract methods** (must implement): `initialize`, `shutdown`, `get_stock_list`, `get_market_data`, `subscribe_quote`
- **15+ optional methods** (raise `NotImplementedError` by default): `get_instrument_detail`, `get_full_tick`, `get_financial_data`, `download_history_data`, `get_trading_dates`, `get_sector_list`, `get_index_weight`, `get_full_kline`, `subscribe_whole_quote`, `get_local_data`, etc.

Factory functions in `__init__.py` (`create_tdx_adapter`, `create_qmt_adapter`) return real or mock adapters based on `settings.is_production` (controlled by `APP_ENV` env var).

### API Routes

| Instance | Method | Path | Description |
|----------|--------|------|-------------|
| TDX | GET | `/api/tdx/stocks?sector=通达信88` | Stock list by sector |
| TDX | GET | `/api/tdx/market-data?stocks=SH600519&fields=Close&period=1d` | Historical market data |
| TDX | WS | `/ws/quote/{client_id}` | Real-time quotes |
| QMT | GET | `/api/qmt/stocks?sector=沪深300` | Stock list by sector |
| QMT | GET | `/api/qmt/market-data?stocks=000001.SZ&fields=close&period=1d` | Historical market data |
| QMT | WS | `/ws/quote/{client_id}` | Real-time quotes |
| Both | GET | `/health` | Health check |

### WebSocket Protocol

Messages use `WSMessage` pydantic model (`src/ws/protocol.py`): `{type, data, timestamp}`. Client sends `{type: "ping"}` for heartbeat, `{type: "subscribe", stocks: [...]}` to subscribe. Server responds with `pong`, `subscribed`, `quote`, or `error`. Connection manager (`src/ws/manager.py`) handles 1-2 NestJS backend connections.

### Directory Layout

```
src/core/          config.py (pydantic-settings), exceptions.py, logging.py
src/adapter/       base.py, factory in __init__.py, tdx/ (real), qmt/ (real), mock/
src/ws/            protocol.py (WSMessage), manager.py (ConnectionManager)
tdx/               main.py, config.py, routes/{market,ws}.py, services/tdx_service.py
qmt/               main.py, config.py, routes/{market,ws}.py, services/qmt_service.py
tests/             conftest.py (httpx ASGI fixtures), unit/, integration/
```

## Key Conventions

- **Config**: `src/core/config.py` — single `settings = AppSettings()` singleton. `APP_ENV=development` selects mock adapters, `production` selects real SDKs.
- **Tests**: `pytest-asyncio` with `asyncio_mode = "auto"` (configured in pyproject.toml). Fixtures in `conftest.py` provide `tdx_client` / `qmt_client` as httpx `AsyncClient` with ASGI transport.
- **Code style**: ruff (line length 100, Python 3.12 target), pyright strict mode, pre-commit hooks.
- **SDK references**: See `TDX.md` for `tqcenter.tq` API, `QMT.md` for `xtquant.xtdata` API.
- **Cross-platform**: macOS development uses mock adapters returning random data. Windows production requires TDX terminal or MiniQMT client running.
- **TDX 策略管理**: 通达信终端用文件路径作为策略名标识。服务重启前必须在通达信终端中**手动删除**已注册的策略, 否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。服务注册身份为 `sdk_path/mist_datasource.py`。
- **Windows 部署**: 使用 `scripts/deploy_windows.ps1` 一键部署 (需管理员权限)。支持 `-SkipService` 跳过服务注册, `-Only install|test|service` 运行单步。
