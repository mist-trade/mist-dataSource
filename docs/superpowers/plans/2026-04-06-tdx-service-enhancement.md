# TDX Service Enhancement Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap all TDX SDK functions in the adapter layer and expose core data APIs as HTTP routes with unified testing.

**Architecture:** Layered approach — (1) migrate base adapter naming, (2) implement all SDK methods in real + mock adapter, (3) add route files, (4) register in main.py, (5) write unit + integration + live tests.

**Tech Stack:** Python 3.12, FastAPI, pydantic, pandas, pytest, httpx

**Spec:** `docs/superpowers/specs/2026-04-06-tdx-service-enhancement-design.md`

---

## File Structure

### New Files
```
tdx/routes/stock.py            — Stock info routes (6 endpoints)
tdx/routes/financial.py        — Financial data routes (3 endpoints)
tdx/routes/value.py            — Sector/stock/market value routes (6 endpoints)
tdx/routes/sector.py           — Sector management routes (7 endpoints)
tdx/routes/etf.py              — ETF/bond routes (3 endpoints)
tdx/routes/client.py           — Client control routes (1 endpoint)
tests/unit/test_tdx_adapter.py — Unit tests for all adapter methods
tests/integration/test_tdx_routes.py — Integration tests for all routes
tests/integration/test_tdx_ws.py     — WebSocket tests
tests/integration/test_tdx_live.py   — Live tests (Windows only)
tests/fixtures/tdx/                  — Fixed test data JSON files
scripts/run_live_tests.ps1           — Live test runner
```

### Modified Files
```
src/adapter/base.py            — Rename get_stock_list, add ~30 method declarations
src/adapter/tdx/client.py      — Implement ~35 SDK methods + ~20 TODO stubs
src/adapter/mock/tdx_mock.py   — Implement ~35 mock methods with fixed data
src/adapter/qmt/client.py      — Rename get_stock_list → get_stock_list_in_sector
src/adapter/mock/qmt_mock.py   — Same rename
qmt/routes/market.py           — Update route to use renamed method
tdx/main.py                    — Register 6 new routers
tdx/routes/market.py           — Add 6 endpoints, rename /stocks
tdx/routes/ws.py               — Rewrite with TDX subscribe_hq
tdx/services/tdx_service.py    — Add service wrappers
```

---

## Task 1: Base Adapter Migration

**Files:**
- Modify: `src/adapter/base.py`
- Modify: `src/adapter/qmt/client.py`
- Modify: `src/adapter/mock/qmt_mock.py`
- Modify: `qmt/routes/market.py`

This task renames the abstract method `get_stock_list` → `get_stock_list_in_sector` and adds a new abstract `get_stock_list(market)`, then updates all consumers (TDX adapter, QMT adapter, QMT mock, QMT routes) to match.

- [ ] **Step 1: Update base adapter**

In `src/adapter/base.py`:
- Rename abstract method `get_stock_list(sector)` → `get_stock_list_in_sector(block_code: str, block_type: int = 0, list_type: int = 0)` with full SDK params
- Add new abstract method `get_stock_list(market: str = "0")` for market-based listing
- Fix existing `get_financial_data` default: change `report_type: str = "report_time"` → `report_type: str = "announce_time"` (match SDK default)
- Update existing `get_sector_list()` to accept `list_type: int = 0` parameter

**IMPORTANT**: The following methods already exist in base.py as optional methods (`raise NotImplementedError`). Do NOT re-declare them — only update signatures if needed:
- `get_divid_factors`, `get_trading_dates`, `get_financial_data` (fix default), `get_sector_list` (add param)
- `get_instrument_detail`, `get_full_tick`, `get_full_kline`, `download_history_data`, `download_history_data2`
- `download_financial_data`, `get_trading_calendar`, `download_sector_data`
- `get_index_weight`, `download_index_weight`, `get_holidays`, `download_holiday_data`
- `get_local_data`, `subscribe_whole_quote`

**Add NEW optional method declarations** (these do NOT exist yet):
  - Market Data: `get_market_snapshot`, `get_gb_info`, `refresh_cache`, `refresh_kline`, `download_file`
  - Stock Info: `get_stock_info`, `get_report_data`, `get_more_info`, `get_relation`
  - Financial: `get_financial_data_by_date`, `get_gp_one_data`
  - Value: `get_bkjy_value`, `get_bkjy_value_by_date`, `get_gpjy_value`, `get_gpjy_value_by_date`, `get_scjy_value`, `get_scjy_value_by_date`
  - Sector: `get_user_sector`, `create_sector`, `delete_sector`, `rename_sector`, `clear_sector`, `send_user_block`
  - ETF: `get_kzz_info`, `get_ipo_info`, `get_trackzs_etf_info`
  - Subscription: `subscribe_hq`, `unsubscribe_hq`, `get_subscribe_list`
  - Client: `exec_to_tdx`
  - Trading stubs: `order_stock`, `cancel_order_stock`, `query_stock_orders`, `query_stock_positions`, `query_stock_asset`, `stock_account`
  - Formula stubs: `formula_format_data`, `formula_set_data`, `formula_set_data_info`, `formula_get_data`, `formula_zb`, `formula_exp`, `formula_xg`, `formula_process`, `formula_process_mul_xg`, `formula_process_mul_zb`
  - Client comm stubs: `send_message`, `send_file`, `send_warn`, `send_bt_data`, `print_to_tdx`

Each new method follows the existing pattern:
```python
async def method_name(self, ...) -> ReturnType:
    """Docstring matching TDX SDK."""
    raise NotImplementedError("method_name not implemented")
```

- [ ] **Step 2: Update QMT adapter**

In `src/adapter/qmt/client.py` line 73: rename `get_stock_list` → `get_stock_list_in_sector`:
```python
async def get_stock_list_in_sector(self, block_code: str = "沪深300", block_type: int = 0, list_type: int = 0) -> list[str]:
    try:
        if list_type == 0:
            return self._xtdata.get_stock_list_in_sector(block_code)
        else:
            # QMT doesn't support list_type=1 natively, return codes only
            return self._xtdata.get_stock_list_in_sector(block_code)
    except Exception as e:
        raise AdapterError(f"Failed to get stock list in sector: {e}") from e
```

- [ ] **Step 3: Update QMT mock adapter**

In `src/adapter/mock/qmt_mock.py` line 24: rename `get_stock_list` → `get_stock_list_in_sector`:
```python
async def get_stock_list_in_sector(self, block_code: str = "沪深300", block_type: int = 0, list_type: int = 0) -> list[str]:
    return ["000001.SZ", "600000.SH", "600519.SH", "601318.SH", "000002.SZ", "000858.SZ", "601398.SH", "600036.SH"]
```

- [ ] **Step 4: Update QMT routes**

In `qmt/routes/market.py` line 15: update to call `get_stock_list_in_sector`:
```python
stocks = await adapter.get_stock_list_in_sector(sector)
```

- [ ] **Step 5: Update TDX adapter**

In `src/adapter/tdx/client.py` line 120: rename `get_stock_list` → `get_stock_list_in_sector` with full params:
```python
async def get_stock_list_in_sector(self, block_code: str = "通达信88", block_type: int = 0, list_type: int = 0) -> list[str]:
    try:
        return self._tq.get_stock_list_in_sector(block_code, block_type, list_type)
    except Exception as e:
        raise AdapterError(f"Failed to get stock list in sector: {e}") from e
```

- [ ] **Step 6: Update TDX mock adapter**

In `src/adapter/mock/tdx_mock.py` line 20: rename `get_stock_list` → `get_stock_list_in_sector`:
```python
async def get_stock_list_in_sector(self, block_code: str = "通达信88", block_type: int = 0, list_type: int = 0) -> list[str]:
    return ["SH000001", "SH600519", "SZ000001", "SH601318", "SZ000858"]
```

Note: This minimal change keeps tests passing until Task 5 fully rewrites the mock adapter.

- [ ] **Step 7: Update TDX service**

In `tdx/services/tdx_service.py` line 17: update to call `get_stock_list_in_sector`:
```python
stocks = await adapter.get_stock_list_in_sector(sector)
```

- [ ] **Step 8: Update existing test files**

These test files reference the old `get_stock_list` name and must be updated:

In `tests/integration/test_tdx_service.py` line 17 and line 20: rename `get_stock_list` → `get_stock_list_in_sector`:
```python
stocks = await adapter.get_stock_list_in_sector(sector)
```

Check if `tests/unit/` contains any test files referencing `get_stock_list` and update those too.

- [ ] **Step 9: Run existing tests to verify no breakage**

Run: `uv run pytest tests/ -v`
Expected: All existing tests pass

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "refactor: rename get_stock_list to get_stock_list_in_sector across all adapters"
```

---

## Task 2: TDX Adapter — Market Data + Stock Info Methods

**Files:**
- Modify: `src/adapter/tdx/client.py`

Implement all market data and stock info methods in the real TDX adapter.

- [ ] **Step 1: Add market data methods**

Add after the existing `subscribe_quote` method (~line 178):

```python
async def get_market_snapshot(self, stock_code: str, field_list: list[str] = []) -> dict:
    """获取实时行情快照. 对应: tq.get_market_snapshot(stock_code, field_list)"""
    try:
        return self._tq.get_market_snapshot(stock_code, field_list)
    except Exception as e:
        raise AdapterError(f"Failed to get market snapshot: {e}") from e

async def get_divid_factors(self, stock_code: str, start_time: str = "", end_time: str = "") -> Any:
    """获取除权除息数据. 对应: tq.get_divid_factors(stock_code, start_time, end_time)"""
    try:
        return self._tq.get_divid_factors(stock_code, start_time, end_time)
    except Exception as e:
        raise AdapterError(f"Failed to get dividend factors: {e}") from e

async def get_gb_info(self, stock_code: str, date_list: list[str] = [], count: int = 1) -> list[dict]:
    """获取股本数据. 对应: tq.get_gb_info(stock_code, date_list, count)"""
    try:
        return self._tq.get_gb_info(stock_code, date_list, count)
    except Exception as e:
        raise AdapterError(f"Failed to get gb info: {e}") from e

async def get_trading_dates(self, market: str = "SH", start_time: str = "", end_time: str = "", count: int = -1) -> list[str]:
    """获取交易日列表. 对应: tq.get_trading_dates(market, start_time, end_time, count)"""
    try:
        return self._tq.get_trading_dates(market, start_time, end_time, count)
    except Exception as e:
        raise AdapterError(f"Failed to get trading dates: {e}") from e

async def refresh_cache(self, market: str = "AG", force: bool = False) -> dict:
    """刷新行情缓存. 对应: tq.refresh_cache(market, force)"""
    try:
        return self._tq.refresh_cache(market, force)
    except Exception as e:
        raise AdapterError(f"Failed to refresh cache: {e}") from e

async def refresh_kline(self, stock_list: list[str] = [], period: str = "1d") -> dict:
    """刷新K线缓存. 对应: tq.refresh_kline(stock_list, period)"""
    try:
        return self._tq.refresh_kline(stock_list, period)
    except Exception as e:
        raise AdapterError(f"Failed to refresh kline: {e}") from e

async def download_file(self, stock_code: str = "", down_time: str = "", down_type: int = 1) -> dict:
    """下载特定数据文件. 对应: tq.download_file(stock_code, down_time, down_type)"""
    try:
        return self._tq.download_file(stock_code, down_time, down_type)
    except Exception as e:
        raise AdapterError(f"Failed to download file: {e}") from e
```

- [ ] **Step 2: Add stock info methods**

```python
async def get_stock_info(self, stock_code: str = "") -> dict:
    """获取股票基本信息. 对应: tq.get_stock_info(stock_code)"""
    try:
        return self._tq.get_stock_info(stock_code)
    except Exception as e:
        raise AdapterError(f"Failed to get stock info: {e}") from e

async def get_report_data(self, stock_code: str = "") -> dict:
    """获取报告数据. 对应: tq.get_report_data(stock_code)"""
    try:
        return self._tq.get_report_data(stock_code)
    except Exception as e:
        raise AdapterError(f"Failed to get report data: {e}") from e

async def get_more_info(self, stock_code: str = "", field_list: list[str] = []) -> dict:
    """获取更多信息. 对应: tq.get_more_info(stock_code, field_list)"""
    try:
        return self._tq.get_more_info(stock_code, field_list)
    except Exception as e:
        raise AdapterError(f"Failed to get more info: {e}") from e

async def get_relation(self, stock_code: str = "") -> dict:
    """获取股票所属板块. 对应: tq.get_relation(stock_code)"""
    try:
        return self._tq.get_relation(stock_code)
    except Exception as e:
        raise AdapterError(f"Failed to get relation: {e}") from e
```

- [ ] **Step 3: Add get_stock_list (market-based)**

```python
async def get_stock_list(self, market: str = "0") -> list[str]:
    """获取指定市场股票列表. 对应: tq.get_stock_list(market)"""
    try:
        return self._tq.get_stock_list(market)
    except Exception as e:
        raise AdapterError(f"Failed to get stock list: {e}") from e
```

- [ ] **Step 4: Commit**

```bash
git add src/adapter/tdx/client.py
git commit -m "feat(tdx): add market data and stock info adapter methods"
```

---

## Task 3: TDX Adapter — Financial + Value Methods

**Files:**
- Modify: `src/adapter/tdx/client.py`

- [ ] **Step 1: Add financial data methods**

```python
async def get_financial_data(
    self, stock_list: list[str], field_list: list[str],
    start_time: str = "", end_time: str = "", report_type: str = "announce_time"
) -> dict:
    """获取专业财务数据. 对应: tq.get_financial_data(stock_list, field_list, start_time, end_time, report_type)"""
    try:
        return self._tq.get_financial_data(stock_list, field_list, start_time, end_time, report_type)
    except Exception as e:
        raise AdapterError(f"Failed to get financial data: {e}") from e

async def get_financial_data_by_date(
    self, stock_list: list[str], field_list: list[str], year: int = 0, mmdd: int = 0
) -> dict:
    """获取指定日期专业财务数据. 对应: tq.get_financial_data_by_date(stock_list, field_list, year, mmdd)"""
    try:
        return self._tq.get_financial_data_by_date(stock_list, field_list, year, mmdd)
    except Exception as e:
        raise AdapterError(f"Failed to get financial data by date: {e}") from e

async def get_gp_one_data(self, stock_list: list[str], field_list: list[str]) -> dict:
    """获取股票单个数据. 对应: tq.get_gp_one_data(stock_list, field_list)"""
    try:
        return self._tq.get_gp_one_data(stock_list, field_list)
    except Exception as e:
        raise AdapterError(f"Failed to get gp one data: {e}") from e
```

- [ ] **Step 2: Add value data methods (bkjy/gpjy/scjy)**

```python
async def get_bkjy_value(self, stock_list: list[str], field_list: list[str], start_time: str = "", end_time: str = "") -> dict:
    """获取板块交易数据. 对应: tq.get_bkjy_value(stock_list, field_list, start_time, end_time)"""
    try:
        return self._tq.get_bkjy_value(stock_list, field_list, start_time, end_time)
    except Exception as e:
        raise AdapterError(f"Failed to get bkjy value: {e}") from e

async def get_bkjy_value_by_date(self, stock_list: list[str], field_list: list[str], year: int = 0, mmdd: int = 0) -> dict:
    """获取指定日期板块交易数据. 对应: tq.get_bkjy_value_by_date(stock_list, field_list, year, mmdd)"""
    try:
        return self._tq.get_bkjy_value_by_date(stock_list, field_list, year, mmdd)
    except Exception as e:
        raise AdapterError(f"Failed to get bkjy value by date: {e}") from e

async def get_gpjy_value(self, stock_list: list[str], field_list: list[str], start_time: str = "", end_time: str = "") -> dict:
    """获取股票交易数据. 对应: tq.get_gpjy_value(stock_list, field_list, start_time, end_time)"""
    try:
        return self._tq.get_gpjy_value(stock_list, field_list, start_time, end_time)
    except Exception as e:
        raise AdapterError(f"Failed to get gpjy value: {e}") from e

async def get_gpjy_value_by_date(self, stock_list: list[str], field_list: list[str], year: int = 0, mmdd: int = 0) -> dict:
    """获取指定日期股票交易数据. 对应: tq.get_gpjy_value_by_date(stock_list, field_list, year, mmdd)"""
    try:
        return self._tq.get_gpjy_value_by_date(stock_list, field_list, year, mmdd)
    except Exception as e:
        raise AdapterError(f"Failed to get gpjy value by date: {e}") from e

async def get_scjy_value(self, field_list: list[str], start_time: str = "", end_time: str = "") -> dict:
    """获取市场交易数据. 对应: tq.get_scjy_value(field_list, start_time, end_time)"""
    try:
        return self._tq.get_scjy_value(field_list, start_time, end_time)
    except Exception as e:
        raise AdapterError(f"Failed to get scjy value: {e}") from e

async def get_scjy_value_by_date(self, field_list: list[str], year: int = 0, mmdd: int = 0) -> dict:
    """获取指定日期市场交易数据. 对应: tq.get_scjy_value_by_date(field_list, year, mmdd)"""
    try:
        return self._tq.get_scjy_value_by_date(field_list, year, mmdd)
    except Exception as e:
        raise AdapterError(f"Failed to get scjy value by date: {e}") from e
```

- [ ] **Step 3: Commit**

```bash
git add src/adapter/tdx/client.py
git commit -m "feat(tdx): add financial data and value data adapter methods"
```

---

## Task 4: TDX Adapter — Sector + ETF + Subscription + Client + Stubs

**Files:**
- Modify: `src/adapter/tdx/client.py`

- [ ] **Step 1: Add sector management methods**

```python
async def get_sector_list(self, list_type: int = 0) -> list:
    """获取A股板块代码列表. 对应: tq.get_sector_list(list_type)"""
    try:
        return self._tq.get_sector_list(list_type)
    except Exception as e:
        raise AdapterError(f"Failed to get sector list: {e}") from e

async def get_user_sector(self) -> list:
    """获取自定义板块列表. 对应: tq.get_user_sector()"""
    try:
        return self._tq.get_user_sector()
    except Exception as e:
        raise AdapterError(f"Failed to get user sector: {e}") from e

# TODO: 以下板块管理方法待后续实现
async def create_sector(self, block_code: str = "", block_name: str = "") -> dict:
    """创建自定义板块. 对应: tq.create_sector(block_code, block_name)"""
    raise NotImplementedError("create_sector not yet implemented")

async def delete_sector(self, block_code: str = "") -> dict:
    """删除自定义板块. 对应: tq.delete_sector(block_code)"""
    raise NotImplementedError("delete_sector not yet implemented")

async def rename_sector(self, block_code: str = "", block_name: str = "") -> dict:
    """重命名自定义板块. 对应: tq.rename_sector(block_code, block_name)"""
    raise NotImplementedError("rename_sector not yet implemented")

async def clear_sector(self, block_code: str = "") -> dict:
    """清空自定义板块成份股. 对应: tq.clear_sector(block_code)"""
    raise NotImplementedError("clear_sector not yet implemented")
```

- [ ] **Step 2: Add ETF/bond methods**

```python
async def get_kzz_info(self, stock_code: str = "", field_list: list[str] = []) -> dict:
    """获取可转债信息. 对应: tq.get_kzz_info(stock_code, field_list)"""
    try:
        return self._tq.get_kzz_info(stock_code, field_list)
    except Exception as e:
        raise AdapterError(f"Failed to get kzz info: {e}") from e

async def get_ipo_info(self, ipo_type: int = 0, ipo_date: int = 0) -> list[dict]:
    """获取新股申购信息. 对应: tq.get_ipo_info(ipo_type, ipo_date)"""
    try:
        return self._tq.get_ipo_info(ipo_type, ipo_date)
    except Exception as e:
        raise AdapterError(f"Failed to get ipo info: {e}") from e

async def get_trackzs_etf_info(self, zs_code: str = "") -> list[dict]:
    """获取跟踪指数的ETF信息. 对应: tq.get_trackzs_etf_info(zs_code)"""
    try:
        return self._tq.get_trackzs_etf_info(zs_code)
    except Exception as e:
        raise AdapterError(f"Failed to get trackzs etf info: {e}") from e
```

- [ ] **Step 3: Add TDX-native subscription methods**

```python
async def subscribe_hq(self, stock_list: list[str], callback) -> dict:
    """订阅股票实时更新. 对应: tq.subscribe_hq(stock_list, callback)"""
    try:
        return self._tq.subscribe_hq(stock_list=stock_list, callback=callback)
    except Exception as e:
        raise AdapterError(f"Failed to subscribe hq: {e}") from e

async def unsubscribe_hq(self, stock_list: list[str] = []) -> dict:
    """取消订阅股票更新. 对应: tq.unsubscribe_hq(stock_list)"""
    try:
        return self._tq.unsubscribe_hq(stock_list=stock_list)
    except Exception as e:
        raise AdapterError(f"Failed to unsubscribe hq: {e}") from e

async def get_subscribe_list(self) -> list[str]:
    """获取当前订阅的股票列表. 对应: tq.get_subscribe_hq_stock_list()"""
    try:
        return self._tq.get_subscribe_hq_stock_list()
    except Exception as e:
        raise AdapterError(f"Failed to get subscribe list: {e}") from e
```

- [ ] **Step 4: Add client control + remaining methods**

```python
async def exec_to_tdx(self, cmd: str = "", param: str = "") -> dict:
    """调用客户端功能接口. 对应: tq.exec_to_tdx(cmd, param)"""
    try:
        return self._tq.exec_to_tdx(cmd, param)
    except Exception as e:
        raise AdapterError(f"Failed to exec to tdx: {e}") from e
```

- [ ] **Step 5: Add TODO stubs (trading, formula, client communication)**

Add all stub methods from spec section "TODO Stubs". Each follows this pattern:

```python
# ===== 交易类 (TODO) =====
async def order_stock(self, account_id: str = "", stock_code: str = "", price: float = 0, amount: int = 0, order_type: int = 0, price_type: int = 0) -> dict:
    """执行股票交易. 对应: tq.order_stock(...)"""
    raise NotImplementedError("order_stock not yet implemented")

# ... (cancel_order_stock, query_stock_orders, query_stock_positions, query_stock_asset, stock_account)

# ===== 公式类 (TODO) =====
async def formula_format_data(self, data_dict: dict = {}) -> list[dict]:
    """格式化K线数据. 对应: tq.formula_format_data(data_dict)"""
    raise NotImplementedError("formula_format_data not yet implemented")

# ... (formula_set_data, formula_set_data_info, formula_get_data, formula_zb, formula_exp, formula_xg, formula_process, formula_process_mul_xg, formula_process_mul_zb)

# ===== 客户端通信类 (TODO) =====
async def send_message(self, msg_str: str = "") -> dict:
    """发送消息到通达信客户端. 对应: tq.send_message(msg_str)"""
    raise NotImplementedError("send_message not yet implemented")

# ... (send_file, send_warn, send_bt_data, print_to_tdx)
```

- [ ] **Step 6: Commit**

```bash
git add src/adapter/tdx/client.py
git commit -m "feat(tdx): add sector, ETF, subscription, client control methods and TODO stubs"
```

---

## Task 5: Mock Adapter — Fixed Data for All Methods

**Files:**
- Modify: `src/adapter/mock/tdx_mock.py`
- Create: `tests/fixtures/tdx/snapshot.json`
- Create: `tests/fixtures/tdx/financial.json`
- Create: `tests/fixtures/tdx/sector_list.json`
- Create: `tests/fixtures/tdx/kzz_info.json`
- Create: `tests/fixtures/tdx/trading_dates.json`

Replace random data with fixed deterministic data. Every method mirrors the real adapter's return format.

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/tdx/` directory and JSON files with fixed data matching SDK return formats. Use exact field names from TDX.md data samples.

- [ ] **Step 2: Rewrite mock adapter**

Replace the entire `src/adapter/mock/tdx_mock.py` with deterministic implementations. Each method returns data matching the SDK format documented in TDX.md "数据样本" sections. Load larger fixtures from JSON, inline simple returns.

**Note**: TheDX mock adapter was renamed in Task 1 Step 6 will be fully replacedeed by this step. That's + "`mock` adapter now has the complete implementation for this task.

Key pattern:
```python
async def get_market_snapshot(self, stock_code: str, field_list: list[str] = []) -> dict:
    return {
        "ItemNum": "3342", "LastClose": "34.21", "Open": "33.78",
        "Max": "36.49", "Min": "32.50", "Now": "35.06",
        "Volume": "122881", "NowVol": "1449", "Amount": "43068.48",
        "Inside": "60373", "Outside": "62509", "TickDiff": "0.00",
        "InOutFlag": "2", "Jjjz": "0.00",
        "Buyp": ["35.05", "35.04", "35.02", "35.01", "35.00"],
        "Buyv": ["154", "9", "49", "136", "154"],
        "Sellp": ["35.06", "35.07", "35.08", "35.09", "35.10"],
        "Sellv": ["4", "31", "139", "4", "4"],
        "UpHome": "0", "DownHome": "0", "Before5MinNow": "35.15",
        "Average": "35.05", "XsFlag": "2", "Zangsu": "-0.25",
        "ZAFPre3": "-1.83", "ErrorId": "0",
    }
```

All methods not yet needing mock data should also raise `NotImplementedError` (matching the TODO stubs in the real adapter).

- [ ] **Step 3: Commit**

```bash
git add src/adapter/mock/tdx_mock.py tests/fixtures/tdx/
git commit -m "feat(tdx): rewrite mock adapter with fixed deterministic data for all methods"
```

---

## Task 6: Routes — Market + Stock

**Files:**
- Modify: `tdx/routes/market.py`
- Create: `tdx/routes/stock.py`

- [ ] **Step 1: Expand market.py routes**

Rename `/stocks` → `/stock-list-in-sector` and add 6 new endpoints to `tdx/routes/market.py`. Follow existing pattern:
- GET handler, validate adapter, call adapter method, return `{"data": result}`
- `stock_list` params: comma-separated → split to list
- `field_list` params: comma-separated → split to list

Add these endpoints:
- `GET /market-snapshot` — params: `stock_code`, `fields` (optional)
- `GET /trading-dates` — params: `market`, `start_time`, `end_time`, `count`
- `GET /divid-factors` — params: `stock_code`, `start_time`, `end_time`
- `GET /gb-info` — params: `stock_code`, `date_list`, `count`
- `POST /refresh-cache` — body: `market`, `force`
- `POST /refresh-kline` — body: `stock_list`, `period`
- `POST /download-file` — body: `stock_code`, `down_time`, `down_type`

- [ ] **Step 2: Create stock.py routes**

Create `tdx/routes/stock.py` with 6 endpoints:
- `GET /stock-list-in-sector` — params: `block_code`, `block_type`, `list_type`
- `GET /stock-list` — params: `market`
- `GET /stock-info` — params: `stock_code`
- `GET /report-data` — params: `stock_code`
- `GET /more-info` — params: `stock_code`, `fields` (optional)
- `GET /relation` — params: `stock_code`

- [ ] **Step 3: Commit**

```bash
git add tdx/routes/market.py tdx/routes/stock.py
git commit -m "feat(tdx): add market and stock route endpoints"
```

---

## Task 7: Routes — Financial + Value + Sector + ETF + Client

**Files:**
- Create: `tdx/routes/financial.py`
- Create: `tdx/routes/value.py`
- Create: `tdx/routes/sector.py`
- Create: `tdx/routes/etf.py`
- Create: `tdx/routes/client.py`

All route files follow the same pattern as existing routes. Each file defines `router = APIRouter()`.

- [ ] **Step 1: Create financial.py**

3 endpoints: `financial-data`, `financial-data-by-date`, `gp-one-data`

- [ ] **Step 2: Create value.py**

6 endpoints: `bkjy-value`, `bkjy-value-by-date`, `gpjy-value`, `gpjy-value-by-date`, `scjy-value`, `scjy-value-by-date`

- [ ] **Step 3: Create sector.py**

7 endpoints: `sector-list`, `user-sectors`, `create-sector`, `delete-sector`, `rename-sector`, `clear-sector`, `send-user-block`

- [ ] **Step 4: Create etf.py**

3 endpoints: `kzz-info`, `ipo-info`, `trackzs-etf-info`

- [ ] **Step 5: Create client.py**

1 endpoint: `exec-to-tdx` (POST, body: `cmd`, `param`)

- [ ] **Step 6: Commit**

```bash
git add tdx/routes/financial.py tdx/routes/value.py tdx/routes/sector.py tdx/routes/etf.py tdx/routes/client.py
git commit -m "feat(tdx): add financial, value, sector, ETF, and client route files"
```

---

## Task 8: Main.py Router Registration + WebSocket Rewrite

**Files:**
- Modify: `tdx/main.py`
- Modify: `tdx/routes/ws.py`

- [ ] **Step 1: Register new routers in main.py**

Add imports and `app.include_router()` for all 6 new route files:

```python
from tdx.routes.stock import router as stock_router
from tdx.routes.financial import router as financial_router
from tdx.routes.value import router as value_router
from tdx.routes.sector import router as sector_router
from tdx.routes.etf import router as etf_router
from tdx.routes.client import router as client_router

app.include_router(stock_router, prefix="/api/tdx", tags=["Stock"])
app.include_router(financial_router, prefix="/api/tdx", tags=["Financial"])
app.include_router(value_router, prefix="/api/tdx", tags=["Value"])
app.include_router(sector_router, prefix="/api/tdx", tags=["Sector"])
app.include_router(etf_router, prefix="/api/tdx", tags=["ETF"])
app.include_router(client_router, prefix="/api/tdx", tags=["Client"])
```

- [ ] **Step 2: Rewrite ws.py with TDX subscribe_hq**

Replace the stub WebSocket handler with TDX-native subscription:
1. On "subscribe" message: validate ≤100 stocks, call `adapter.subscribe_hq(stocks, callback)`
2. Callback bridges sync→async via `asyncio.Queue`
3. Async consumer task reads queue, calls `get_market_snapshot`, broadcasts
4. On "unsubscribe" message: call `adapter.unsubscribe_hq(stocks)`

- [ ] **Step 3: Verify app starts**

Run: `uv run uvicorn tdx.main:app --port 9001 --reload`
Expected: App starts, all routes appear in `/docs`

- [ ] **Step 4: Commit**

```bash
git add tdx/main.py tdx/routes/ws.py
git commit -m "feat(tdx): register all routers and implement TDX-native WebSocket subscription"
```

---

## Task 9: Service Layer Update

**Files:**
- Modify: `tdx/services/tdx_service.py`

**IMPORTANT**: Routes call adapter methods **directly** (same as existing pattern in `market.py`). The service layer is only used by `TDXService` for composite methods like `get_sector_overview`. Individual routes do not go through the service. The service layer exists for future composition queries and business logic.

- [ ] **Step 1: Add DataFrame serialization helper**

```python
def _serialize_df(df) -> Any:
    """Serialize DataFrame to JSON-compatible dict."""
    if hasattr(df, "to_dict"):
        return df.to_dict(orient="records")
    return df

def _serialize_result(result: Any) -> Any:
    """Recursively serialize DataFrames in result."""
    if isinstance(result, dict):
        return {k: _serialize_result(v) for k, v in result.items()}
    if isinstance(result, list):
        return [_serialize_result(item) for item in result]
    if hasattr(result, "to_dict"):
        return result.to_dict(orient="records")
    return result
```

- [ ] **Step 2: Add thin service wrappers**

For each new adapter method, add a service method that:
1. Gets adapter from `tdx.main.tdx_adapter`
2. Validates adapter is initialized
3. Calls adapter method
4. Serializes DataFrames via `_serialize_result`
5. Returns result

The service methods are thin wrappers — no business logic beyond serialization and validation.

- [ ] **Step 3: Commit**

```bash
git add tdx/services/tdx_service.py
git commit -m "feat(tdx): add service layer wrappers with DataFrame serialization"
```

---

## Task 10: Unit Tests — Adapter Methods

**Files:**
- Create: `tests/unit/test_tdx_adapter.py`

- [ ] **Step 1: Write adapter unit tests**

Test every implemented method on the mock adapter. Each test:
1. Creates `TDXMockAdapter`, calls `initialize()`
2. Calls method with valid params
3. Asserts return type and key fields match SDK spec

```python
import pytest
from src.adapter.mock.tdx_mock import TDXMockAdapter

@pytest.fixture
async def adapter():
    a = TDXMockAdapter()
    await a.initialize()
    yield a
    await a.shutdown()

@pytest.mark.asyncio
async def test_get_market_snapshot(adapter):
    result = await adapter.get_market_snapshot("SH600519")
    assert isinstance(result, dict)
    assert "Now" in result
    assert "Buyp" in result
    assert "ErrorId" in result

@pytest.mark.asyncio
async def test_get_stock_list_in_sector(adapter):
    result = await adapter.get_stock_list_in_sector("通达信88")
    assert isinstance(result, list)
    assert len(result) > 0

@pytest.mark.asyncio
async def test_get_stock_list(adapter):
    result = await adapter.get_stock_list("0")
    assert isinstance(result, list)
    assert len(result) > 0

# ... one test per method
```

- [ ] **Step 2: Run unit tests**

Run: `uv run pytest tests/unit/test_tdx_adapter.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_tdx_adapter.py
git commit -m "test(tdx): add unit tests for all adapter methods"
```

---

## Task 11: Integration Tests — Routes

**Files:**
- Create: `tests/integration/test_tdx_routes.py`

- [ ] **Step 1: Write route integration tests**

Using `tdx_client` fixture from `conftest.py`, test every endpoint:

```python
import pytest

@pytest.mark.asyncio
async def test_stock_list_in_sector(tdx_client):
    resp = await tdx_client.get("/api/tdx/stock-list-in-sector?block_code=通达信88")
    assert resp.status_code == 200
    data = resp.json()
    assert "stocks" in data or "data" in data

@pytest.mark.asyncio
async def test_market_snapshot(tdx_client):
    resp = await tdx_client.get("/api/tdx/market-snapshot?stock_code=SH600519")
    assert resp.status_code == 200

@pytest.mark.asyncio
async def test_financial_data(tdx_client):
    resp = await tdx_client.get("/api/tdx/financial-data?stocks=SH600519&fields=FN2,FN7")
    assert resp.status_code == 200

# ... one test per endpoint (~30 endpoints)
```

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/integration/test_tdx_routes.py -v`
Expected: All tests pass

- [ ] **Step 3: Update existing integration tests**

Update `tests/integration/test_tdx_service.py` to use `get_stock_list_in_sector` instead of `get_stock_list`.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v --ignore=tests/integration/test_tdx_live.py`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_tdx_routes.py tests/integration/test_tdx_service.py
git commit -m "test(tdx): add integration tests for all route endpoints"
```

---

## Task 12: WebSocket Tests

**Files:**
- Create: `tests/integration/test_tdx_ws.py`

- [ ] **Step 1: Write WebSocket tests**

Using FastAPI's `TestClient` (sync, supports WebSocket):

```python
from starlette.testclient import TestClient
from tdx.main import app

def test_ws_ping_pong():
    client = TestClient(app)
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"

def test_ws_subscribe_limit():
    """超过100只股票应返回错误"""
    client = TestClient(app)
    stocks = [f"SH{i:06d}" for i in range(101)]
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        # 应收到错误或 subscribed 消息
```

- [ ] **Step 2: Run WebSocket tests**

Run: `uv run pytest tests/integration/test_tdx_ws.py -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tdx_ws.py
git commit -m "test(tdx): add WebSocket integration tests"
```

---

## Task 13: Live Test Script + Final Verification

**Files:**
- Create: `tests/integration/test_tdx_live.py`
- Create: `scripts/run_live_tests.ps1`

- [ ] **Step 1: Create live test file**

Mark all tests with `@pytest.mark.live`. Test each adapter method with real stock code `SH600519`:

```python
import pytest

@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_market_snapshot():
    from src.adapter import create_tdx_adapter
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_market_snapshot("SH600519")
        assert isinstance(result, dict)
        assert "Now" in result
    finally:
        await adapter.shutdown()

# ... one live test per implemented method
```

- [ ] **Step 2: Create PowerShell runner script**

```powershell
# scripts/run_live_tests.ps1
$env:APP_ENV = "production"
pytest tests/integration/test_tdx_live.py -v -m live
```

- [ ] **Step 3: Run full test suite (non-live)**

Run: `uv run pytest tests/ -v --ignore=tests/integration/test_tdx_live.py`
Expected: All pass

- [ ] **Step 4: Lint check**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: No errors

- [ ] **Step 5: Final commit**

```bash
git add tests/integration/test_tdx_live.py scripts/run_live_tests.ps1
git commit -m "test(tdx): add live integration tests and Windows runner script"
```
