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
NestJS backend → HTTP /api/{tdx|qmt}/* → routes/ → adapter (module global in main.py)
                → WebSocket /ws/quote/{client_id} → ws_manager.broadcast()
```

### Module-Level Singletons

Each `main.py` holds module-level globals: `{tdx|qmt}_adapter` (adapter instance) and `ws_manager` (WebSocket connection manager). Routes access these via a `_get_adapter()` helper that imports from the main module to avoid circular dependencies:

```python
def _get_adapter():
    import tdx.main
    return tdx.main.tdx_adapter
```

Services use singleton pattern (e.g., `tdx_service = TDXService()` in `tdx/services/`).

### Adapter Pattern (`src/adapter/`)

`base.py` defines `MarketDataAdapter` abstract base class with 70+ methods:

**Required abstract methods** (must implement):
- `initialize()` - Initialize SDK connection
- `shutdown()` - Close SDK connection
- `get_stock_list(market)` - Get all stocks in market
- `get_stock_list_in_sector(block_code, block_type, list_type)` - Get stocks by sector
- `get_market_data(stock_list, fields, period, start_time, end_time, **kwargs)` - Historical K-line data
- `subscribe_quote(stock_list)` - AsyncIterator for real-time quotes

**Optional methods** (raise `NotImplementedError` by default):
- Market data: `get_market_snapshot`, `get_full_tick`, `get_divid_factors`, `get_trading_dates`, `get_gb_info`, `refresh_cache`, `refresh_kline`, `download_file`, `get_local_data`
- Instrument info: `get_instrument_detail`, `get_instrument_type`, `get_stock_info`
- Financial: `get_financial_data`, `download_financial_data`, `get_financial_data_by_date`
- Sectors: `get_sector_list`, `download_sector_data`, `get_index_weight`, `download_index_weight`
- User sectors: `get_user_sector`, `create_sector`, `delete_sector`, `rename_sector`
- ETF: `get_kzz_info`, `get_ipo_info`, `get_trackzs_etf_info`
- Subscription: `subscribe_hq`, `unsubscribe_hq`, `get_subscribe_list`
- Trading: `order_stock`, `cancel_order_stock`, `query_stock_orders`, `query_stock_positions`, `query_stock_asset`
- Formula: `formula_zb`, `formula_exp`, `formula_xg`
- Client comm: `exec_to_tdx`, `send_message`, `print_to_tdx`

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
src/adapter/       base.py (MarketDataAdapter ABC), factory in __init__.py, tdx/, qmt/, mock/
src/ws/            protocol.py (WSMessage), manager.py (ConnectionManager)
tdx/               main.py, config.py, routes/{market,stock,financial,value,sector,etf,client,ws}.py, services/tdx_service.py
qmt/               main.py, config.py, routes/{market,ws}.py, services/qmt_service.py
tests/             conftest.py (httpx ASGI fixtures that auto-init adapters), unit/, integration/
```

## Key Conventions

- **Config**: `src/core/config.py` — single `settings = AppSettings()` singleton. `APP_ENV=development` selects mock adapters, `production` selects real SDKs.
- **Tests**: `pytest-asyncio` with `asyncio_mode = "auto"` (configured in pyproject.toml). Fixtures in `conftest.py` provide `tdx_client` / `qmt_client` as httpx `AsyncClient` with ASGI transport. These fixtures automatically initialize the adapter before yielding and shut it down in cleanup.
- **Code style**: ruff (line length 100, Python 3.12 target), pyright strict mode, pre-commit hooks.
- **SDK references**: See `TDX.md` for `tqcenter.tq` API, `QMT.md` for `xtquant.xtdata` API.
- **Cross-platform**: macOS development uses mock adapters returning random data. Windows production requires TDX terminal or MiniQMT client running.
- **TDX 策略管理**: 通达信终端用文件路径作为策略名标识。服务重启前必须在通达信终端中**手动删除**已注册的策略, 否则 `tq.initialize()` 会报 "已有同名策略运行" 导致初始化失败。服务注册身份为 `sdk_path/mist_datasource.py`。
- **Windows 部署**: 使用 `scripts/deploy_windows.ps1` 一键部署 (需管理员权限)。支持 `-SkipService` 跳过服务注册, `-Only install|test|service` 运行单步。
