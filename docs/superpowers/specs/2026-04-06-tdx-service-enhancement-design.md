# TDX Service Enhancement Design

## Overview

Full-scope enhancement of the TDX adapter in mist-datasource to wrap all SDK functions documented in `TDX.md`. The approach is layered: adapter layer first (all SDK functions), then routes (data access APIs), with unified testing.

## Guiding Principles

1. **Naming**: Route paths (kebab-case) and adapter method names directly mirror SDK function names (e.g., `get_market_snapshot` → `/api/tdx/market-snapshot`). No translation layer.
2. **Existing routes renamed**: Since no consumers exist yet, rename `/api/tdx/stocks` → `/api/tdx/stock-list-in-sector` for consistency.
3. **Adapter stubs for future functions**: Trading, formula, and client communication functions get `raise NotImplementedError` stubs with TODO comments so nothing is forgotten.
4. **Fixed mock data**: Mock adapter returns deterministic data (not random) for reproducible unit tests.
5. **TDX-native WebSocket**: Use `tq.subscribe_hq` (notification) → `tq.get_market_snapshot` (pull) → broadcast pattern, distinct from QMT's direct-push approach.

## Phase 1: Adapter Layer (All SDK Functions)

### 1.1 Base Adapter Update (`src/adapter/base.py`)

Add optional method declarations for all new functions. Each method has clear parameter types and return type hints.

### 1.2 Real TDX Adapter (`src/adapter/tdx/client.py`)

#### Market Data Functions (7 new)

| Method | SDK Call | Parameters | Return |
|--------|----------|------------|--------|
| `get_market_snapshot` | `tq.get_market_snapshot()` | `stock_code: str, field_list: list[str]` | `dict` |
| `get_divid_factors` | `tq.get_divid_factors()` | `stock_code: str, start_time: str, end_time: str` | `pd.DataFrame` |
| `get_gb_info` | `tq.get_gb_info()` | `stock_code: str, date_list: list[str], count: int` | `list[dict]` |
| `get_trading_dates` | `tq.get_trading_dates()` | `market: str, start_time: str, end_time: str, count: int` | `list[str]` |
| `refresh_cache` | `tq.refresh_cache()` | `market: str, force: bool` | `dict` |
| `refresh_kline` | `tq.refresh_kline()` | `stock_list: list[str], period: str` | `dict` |
| `download_file` | `tq.download_file()` | `stock_code: str, down_time: str, down_type: int` | `dict` |

#### Stock Info Functions (4 new)

| Method | SDK Call | Parameters | Return |
|--------|----------|------------|--------|
| `get_stock_info` | `tq.get_stock_info()` | `stock_code: str` | `dict` |
| `get_report_data` | `tq.get_report_data()` | `stock_code: str` | `dict` |
| `get_more_info` | `tq.get_more_info()` | `stock_code: str, field_list: list[str]` | `dict` |
| `get_relation` | `tq.get_relation()` | `stock_code: str` | `dict` |

#### Financial Data Functions (3 new)

| Method | SDK Call | Parameters | Return |
|--------|----------|------------|--------|
| `get_financial_data` | `tq.get_financial_data()` | `stock_list, field_list, start_time, end_time, report_type` | `dict[str, pd.DataFrame]` |
| `get_financial_data_by_date` | `tq.get_financial_data_by_date()` | `stock_list, field_list, year, mmdd` | `dict` |
| `get_gp_one_data` | `tq.get_gp_one_data()` | `stock_list, field_list` | `dict` |

#### Sector/Market Value Functions (6 new)

| Method | SDK Call | Parameters | Return |
|--------|----------|------------|--------|
| `get_bkjy_value` | `tq.get_bkjy_value()` | `stock_list, field_list, start_time, end_time` | `dict` |
| `get_bkjy_value_by_date` | `tq.get_bkjy_value_by_date()` | `stock_list, field_list, year, mmdd` | `dict` |
| `get_gpjy_value` | `tq.get_gpjy_value()` | `stock_list, field_list, start_time, end_time` | `dict` |
| `get_gpjy_value_by_date` | `tq.get_gpjy_value_by_date()` | `stock_list, field_list, year, mmdd` | `dict` |
| `get_scjy_value` | `tq.get_scjy_value()` | `field_list, start_time, end_time` | `dict` |
| `get_scjy_value_by_date` | `tq.get_scjy_value_by_date()` | `field_list, year, mmdd` | `dict` |

#### Sector Management Functions (7 new)

| Method | SDK Call | Status |
|--------|----------|--------|
| `get_sector_list` | `tq.get_sector_list()` | Implement |
| `get_user_sector` | `tq.get_user_sector()` | Implement |
| `get_stock_list` | `tq.get_stock_list()` | Implement |
| `create_sector` | `tq.create_sector()` | TODO stub |
| `delete_sector` | `tq.delete_sector()` | TODO stub |
| `rename_sector` | `tq.rename_sector()` | TODO stub |
| `clear_sector` | `tq.clear_sector()` | TODO stub |

#### ETF/Bond Functions (3 new)

| Method | SDK Call | Parameters | Return |
|--------|----------|------------|--------|
| `get_kzz_info` | `tq.get_kzz_info()` | `stock_code, field_list` | `dict` |
| `get_ipo_info` | `tq.get_ipo_info()` | `ipo_type, ipo_date` | `list[dict]` |
| `get_trackzs_etf_info` | `tq.get_trackzs_etf_info()` | `zs_code: str` | `list[dict]` |

#### Real-time Subscription (TDX-native approach, 3 new)

| Method | SDK Call | Description |
|--------|----------|-------------|
| `subscribe_hq` | `tq.subscribe_hq()` | Register callback for stock updates |
| `unsubscribe_hq` | `tq.unsubscribe_hq()` | Remove subscription |
| `get_subscribe_list` | `tq.get_subscribe_hq_stock_list()` | Get subscribed stocks |

TDX's subscription model differs from QMT:
- `subscribe_hq(stock_list, callback)` fires a callback when data changes
- The callback receives `{"Code": "XXXXXX.XX", "ErrorId": "0"}`
- Adapter then calls `get_market_snapshot(code)` to pull full data
- Bridge to async via queue/callback, then broadcast to WebSocket clients

#### TODO Stubs (not implemented, raise NotImplementedError)

**Trading (6):** `order_stock`, `cancel_order_stock`, `query_stock_orders`, `query_stock_positions`, `query_stock_asset`, `stock_account`

**Formula (9):** `formula_format_data`, `formula_set_data`, `formula_set_data_info`, `formula_get_data`, `formula_zb`, `formula_exp`, `formula_xg`, `formula_process`, `formula_process_mul_xg`, `formula_process_mul_zb`

**Client Communication (5):** `send_message`, `send_file`, `send_warn`, `send_bt_data`, `print_to_tdx`

### 1.3 Mock Adapter (`src/adapter/mock/tdx_mock.py`)

Every new method returns **fixed, deterministic** data matching the SDK's return format. Examples:

```python
def get_market_snapshot(self, stock_code: str, field_list: list[str] = []) -> dict:
    return {
        "LastClose": "34.21", "Open": "33.78", "Now": "35.06",
        "Max": "36.49", "Min": "32.50", "Volume": "122881",
        "Buyp": ["35.05", "35.04", "35.02", "35.01", "35.00"],
        "Sellp": ["35.06", "35.07", "35.08", "35.09", "35.10"],
        # ... full snapshot structure
    }

def get_financial_data(self, stock_list, field_list, start_time, end_time, report_type):
    return {"SH600519": pd.DataFrame({...})}  # fixed data
```

## Phase 2: Route Layer

### 2.1 Route Files and Endpoints

Each route path (kebab-case) directly maps to the adapter method name. Parameter names match SDK parameter names.

**`tdx/routes/market.py` (existing, expanded):**

| Method | Path | Adapter Call |
|--------|------|-------------|
| GET | `/api/tdx/market-data` | `get_market_data()` |
| GET | `/api/tdx/market-snapshot` | `get_market_snapshot()` |
| GET | `/api/tdx/trading-dates` | `get_trading_dates()` |
| GET | `/api/tdx/divid-factors` | `get_divid_factors()` |
| GET | `/api/tdx/gb-info` | `get_gb_info()` |
| POST | `/api/tdx/refresh-cache` | `refresh_cache()` |
| POST | `/api/tdx/refresh-kline` | `refresh_kline()` |
| POST | `/api/tdx/download-file` | `download_file()` |

**`tdx/routes/stock.py` (new):**

| Method | Path | Adapter Call |
|--------|------|-------------|
| GET | `/api/tdx/stock-list-in-sector` | `get_stock_list_in_sector()` (renamed from `/stocks`) |
| GET | `/api/tdx/stock-list` | `get_stock_list()` |
| GET | `/api/tdx/stock-info` | `get_stock_info()` |
| GET | `/api/tdx/report-data` | `get_report_data()` |
| GET | `/api/tdx/more-info` | `get_more_info()` |
| GET | `/api/tdx/relation` | `get_relation()` |

**`tdx/routes/financial.py` (new):**

| Method | Path | Adapter Call |
|--------|------|-------------|
| GET | `/api/tdx/financial-data` | `get_financial_data()` |
| GET | `/api/tdx/financial-data-by-date` | `get_financial_data_by_date()` |
| GET | `/api/tdx/gp-one-data` | `get_gp_one_data()` |

**`tdx/routes/value.py` (new):**

| Method | Path | Adapter Call |
|--------|------|-------------|
| GET | `/api/tdx/bkjy-value` | `get_bkjy_value()` |
| GET | `/api/tdx/bkjy-value-by-date` | `get_bkjy_value_by_date()` |
| GET | `/api/tdx/gpjy-value` | `get_gpjy_value()` |
| GET | `/api/tdx/gpjy-value-by-date` | `get_gpjy_value_by_date()` |
| GET | `/api/tdx/scjy-value` | `get_scjy_value()` |
| GET | `/api/tdx/scjy-value-by-date` | `get_scjy_value_by_date()` |

**`tdx/routes/sector.py` (new):**

| Method | Path | Adapter Call |
|--------|------|-------------|
| GET | `/api/tdx/sector-list` | `get_sector_list()` |
| GET | `/api/tdx/user-sectors` | `get_user_sector()` |
| POST | `/api/tdx/create-sector` | `create_sector()` |
| POST | `/api/tdx/delete-sector` | `delete_sector()` |
| POST | `/api/tdx/rename-sector` | `rename_sector()` |
| POST | `/api/tdx/clear-sector` | `clear_sector()` |
| POST | `/api/tdx/send-user-block` | `send_user_block()` (moved from market.py) |

**`tdx/routes/etf.py` (new):**

| Method | Path | Adapter Call |
|--------|------|-------------|
| GET | `/api/tdx/kzz-info` | `get_kzz_info()` |
| GET | `/api/tdx/ipo-info` | `get_ipo_info()` |
| GET | `/api/tdx/trackzs-etf-info` | `get_trackzs_etf_info()` |

**`tdx/routes/ws.py` (existing, rewrite subscription):**

```
WS /ws/quote/{client_id}
```

Uses TDX-native pattern:
1. Client sends `{type: "subscribe", stocks: [...]}`
2. Route calls `adapter.subscribe_hq(stocks, callback)`
3. Callback fires → `adapter.get_market_snapshot(code)` → `ws_manager.broadcast()`
4. Client sends `{type: "unsubscribe", stocks: [...]}` → `adapter.unsubscribe_hq(stocks)`

### 2.2 Route Parameter Conventions

- GET endpoints use query parameters
- POST endpoints accept JSON body
- Parameter names match SDK parameter names (e.g., `stock_code`, `field_list`, `start_time`)
- `stock_list` parameters accept comma-separated string in query, split to list
- `field_list` parameters accept comma-separated string in query, split to list
- Response format: `{"success": true, "data": {...}, "message": ""}`

### 2.3 TDX Service Layer Update

`tdx/services/tdx_service.py` gains thin wrapper methods for each new function. Service layer handles:
- Parameter validation (required vs optional)
- Response normalization (ensure consistent JSON-serializable output)
- Error wrapping (catch SDK errors, return structured error response)

## Phase 3: Testing

### 3.1 Unit Tests (macOS, mock adapter)

File: `tests/unit/test_tdx_adapter.py`

For each adapter method:
- Test with valid parameters → verify return format matches SDK spec
- Test with missing required parameters → verify appropriate error
- Mock adapter returns fixed data, assertions are deterministic

File: `tests/unit/test_tdx_mock_adapter.py`

Verify mock adapter returns the exact fixed data structures for all new methods.

### 3.2 Route Integration Tests (macOS, mock adapter)

File: `tests/integration/test_tdx_routes.py`

For each route endpoint:
- Test GET with query params → verify HTTP 200 and response schema
- Test POST with JSON body → verify HTTP 200 and response schema
- Test missing required params → verify HTTP 422

### 3.3 Live Integration Tests (Windows, real TDX terminal)

File: `tests/integration/test_tdx_live.py`

- Marked with `@pytest.mark.live`
- Requires `APP_ENV=production` and running TDX terminal
- Tests every adapter method with real stock codes (e.g., `SH600519`)
- Runner script: `scripts/run_live_tests.ps1`
- Validates actual data structure matches SDK documentation

### 3.4 Test Data

Mock test data lives in `tests/fixtures/tdx/`:
- `snapshot.json` — fixed market snapshot data
- `financial.json` — fixed financial data
- `sector_list.json` — fixed sector list
- `kzz_info.json` — fixed convertible bond data
- etc.

## File Changes Summary

### New Files
- `tdx/routes/stock.py`
- `tdx/routes/financial.py`
- `tdx/routes/value.py`
- `tdx/routes/sector.py`
- `tdx/routes/etf.py`
- `tests/unit/test_tdx_adapter.py`
- `tests/unit/test_tdx_mock_adapter.py`
- `tests/integration/test_tdx_routes.py`
- `tests/integration/test_tdx_live.py`
- `tests/fixtures/tdx/*.json`
- `scripts/run_live_tests.ps1`

### Modified Files
- `src/adapter/base.py` — add optional method declarations
- `src/adapter/tdx/client.py` — implement all new methods + TODO stubs
- `src/adapter/mock/tdx_mock.py` — implement all new methods with fixed data
- `tdx/main.py` — register new routers
- `tdx/routes/market.py` — expand with new endpoints, remove moved ones
- `tdx/routes/ws.py` — rewrite to use TDX subscribe_hq
- `tdx/services/tdx_service.py` — add service methods

### Renamed Routes
- `/api/tdx/stocks` → `/api/tdx/stock-list-in-sector`
