# QMT 服务 API 重建实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 QMT 服务从 2 个端点扩展到 34 个，路由结构对齐 TDX，行情模块完整实现，交易模块保留 NotImplementedError 存根。同时精简 base.py 为最小抽象基类。

**Architecture:** base.py 仅保留 `initialize()` + `shutdown()` 抽象方法。QMT adapter 自行定义全部方法（方法名映射 xtdata/xttrader SDK），TDX adapter 不变（已定义所有方法）。每个路由文件通过 `_get_adapter()` 延迟导入 `qmt.main.qmt_adapter`。QMTMockAdapter 为 macOS 开发提供 mock 数据。

**Tech Stack:** FastAPI, pydantic, httpx (测试), pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-09-qmt-api-rebuild-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `src/adapter/base.py` | 精简为仅 `initialize()` + `shutdown()` 抽象方法 |
| Modify | `src/adapter/qmt/client.py` | 新增 ~30 个行情方法 + 交易存根 |
| Modify | `src/adapter/mock/qmt_mock.py` | 新增 ~30 个 mock 行情方法 |
| Rewrite | `qmt/routes/market.py` | 13 个行情端点 |
| Create | `qmt/routes/stock.py` | 2 个合约信息端点 |
| Create | `qmt/routes/financial.py` | 3 个财务数据端点 |
| Create | `qmt/routes/sector.py` | 10 个板块管理端点 |
| Create | `qmt/routes/etf.py` | 5 个 ETF/可转债/IPO 端点 |
| Modify | `qmt/main.py` | 注册 5 个新路由 |
| Modify | `tests/conftest.py` | 修复 qmt_client fixture |
| Create | `tests/integration/test_qmt_routes.py` | QMT 路由集成测试 |

---

## Task 1: 精简 base.py

**Files:**
- Modify: `src/adapter/base.py`

- [ ] **Step 1: 重写 base.py**

将当前 910 行的 base.py 精简为仅保留 `initialize()` + `shutdown()` 两个抽象方法。TDX adapter 已自行定义所有 TDX 方法，不依赖 base.py 方法存根。QMT adapter 同理。

```python
"""Base adapter abstract class for market data providers."""

from abc import ABC, abstractmethod


class MarketDataAdapter(ABC):
    """交易引擎适配器基类.

    仅定义 initialize/shutdown 抽象方法。
    TDX/QMT 各自在自己的 adapter 中定义全部方法，不共享签名。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """初始化连接."""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭连接."""
```

- [ ] **Step 2: 验证 TDX 测试不受影响**

```bash
uv run pytest tests/ -v -k "tdx"
```

Expected: PASS（TDX adapter 已自行定义所有方法，不依赖 base.py 存根）

- [ ] **Step 3: Commit**

```bash
git add src/adapter/base.py
git commit -m "refactor: simplify base adapter to initialize/shutdown only"
```

---

## Task 2: 扩展 QMTAdapter 实现行情方法

**Files:**
- Modify: `src/adapter/qmt/client.py`

- [ ] **Step 1: 添加行情数据方法**

在 `subscribe_quote` 方法之后添加以下方法，每个方法直接映射到 `self._xtdata` 对应函数：

```python
    # ---- 行情扩展接口 (xtdata) ----

    async def get_local_data(self, stock_list, fields, period="1d", start_time="", end_time="", **kwargs):
        try:
            dividend_type = kwargs.get("dividend_type", "none")
            count = kwargs.get("count", -1)
            fill_data = kwargs.get("fill_data", True)
            return self._xtdata.get_local_data(
                field_list=fields, stock_list=stock_list, period=period,
                start_time=start_time, end_time=end_time, count=count,
                dividend_type=dividend_type, fill_data=fill_data,
            )
        except Exception as e:
            raise AdapterError(f"Failed to get local data: {e}") from e

    async def get_full_tick(self, code_list: list[str]) -> dict[str, Any]:
        try:
            return self._xtdata.get_full_tick(code_list)
        except Exception as e:
            raise AdapterError(f"Failed to get full tick: {e}") from e

    async def get_full_kline(self, stock_list, period="1m", fields=None, start_time="", end_time="", count=1, dividend_type="none"):
        try:
            return self._xtdata.get_full_kline(
                field_list=fields or [], stock_list=stock_list, period=period,
                start_time=start_time, end_time=end_time, count=count,
                dividend_type=dividend_type,
            )
        except Exception as e:
            raise AdapterError(f"Failed to get full kline: {e}") from e

    async def get_divid_factors(self, stock_code, start_time="", end_time=""):
        try:
            return self._xtdata.get_divid_factors(stock_code, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get divid factors: {e}") from e

    async def download_history_data(self, stock_code, period, start_time="", end_time="", incrementally=None):
        try:
            self._xtdata.download_history_data(stock_code, period, start_time, end_time, incrementally)
        except Exception as e:
            raise AdapterError(f"Failed to download history data: {e}") from e

    async def download_history_data2(self, stock_list, period, start_time="", end_time=""):
        try:
            self._xtdata.download_history_data2(stock_list, period, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to batch download history data: {e}") from e

    async def get_trading_dates(self, market, start_time="", end_time="", count=-1):
        try:
            return self._xtdata.get_trading_dates(market, start_time, end_time, count)
        except Exception as e:
            raise AdapterError(f"Failed to get trading dates: {e}") from e

    async def get_trading_calendar(self, market, start_time="", end_time=""):
        try:
            return self._xtdata.get_trading_calendar(market, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get trading calendar: {e}") from e

    async def get_holidays(self):
        try:
            return self._xtdata.get_holidays()
        except Exception as e:
            raise AdapterError(f"Failed to get holidays: {e}") from e

    async def download_holiday_data(self):
        try:
            self._xtdata.download_holiday_data()
        except Exception as e:
            raise AdapterError(f"Failed to download holiday data: {e}") from e

    async def get_period_list(self):
        try:
            return self._xtdata.get_period_list()
        except Exception as e:
            raise AdapterError(f"Failed to get period list: {e}") from e
```

- [ ] **Step 2: 添加合约信息和财务数据方法**

```python
    # ---- 合约信息接口 (xtdata) ----

    async def get_instrument_detail(self, stock_code, iscomplete=False):
        try:
            return self._xtdata.get_instrument_detail(stock_code, iscomplete)
        except Exception as e:
            raise AdapterError(f"Failed to get instrument detail: {e}") from e

    async def get_instrument_type(self, stock_code):
        try:
            return self._xtdata.get_instrument_type(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get instrument type: {e}") from e

    # ---- 财务数据接口 (xtdata) ----

    async def get_financial_data(self, stock_list, table_list=None, start_time="", end_time="", report_type="report_time"):
        try:
            return self._xtdata.get_financial_data(stock_list, table_list or [], start_time, end_time, report_type)
        except Exception as e:
            raise AdapterError(f"Failed to get financial data: {e}") from e

    async def download_financial_data(self, stock_list, table_list=None):
        try:
            self._xtdata.download_financial_data(stock_list, table_list or [])
        except Exception as e:
            raise AdapterError(f"Failed to download financial data: {e}") from e

    async def download_financial_data2(self, stock_list, table_list=None, start_time="", end_time=""):
        try:
            self._xtdata.download_financial_data2(stock_list, table_list or [], start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to batch download financial data: {e}") from e
```

- [ ] **Step 3: 添加板块管理方法**

```python
    # ---- 板块管理接口 (xtdata) ----

    async def get_sector_list(self):
        try:
            return self._xtdata.get_sector_list()
        except Exception as e:
            raise AdapterError(f"Failed to get sector list: {e}") from e

    async def download_sector_data(self):
        try:
            self._xtdata.download_sector_data()
        except Exception as e:
            raise AdapterError(f"Failed to download sector data: {e}") from e

    async def get_index_weight(self, index_code):
        try:
            return self._xtdata.get_index_weight(index_code)
        except Exception as e:
            raise AdapterError(f"Failed to get index weight: {e}") from e

    async def download_index_weight(self):
        try:
            self._xtdata.download_index_weight()
        except Exception as e:
            raise AdapterError(f"Failed to download index weight: {e}") from e

    async def create_sector_folder(self, parent_node, folder_name, overwrite=True):
        try:
            return self._xtdata.create_sector_folder(parent_node, folder_name, overwrite)
        except Exception as e:
            raise AdapterError(f"Failed to create sector folder: {e}") from e

    async def create_sector(self, parent_node="", sector_name="", overwrite=True):
        try:
            return self._xtdata.create_sector(parent_node, sector_name, overwrite)
        except Exception as e:
            raise AdapterError(f"Failed to create sector: {e}") from e

    async def add_sector(self, sector_name, stock_list):
        try:
            self._xtdata.add_sector(sector_name, stock_list)
        except Exception as e:
            raise AdapterError(f"Failed to add sector: {e}") from e

    async def remove_stock_from_sector(self, sector_name, stock_list):
        try:
            return self._xtdata.remove_stock_from_sector(sector_name, stock_list)
        except Exception as e:
            raise AdapterError(f"Failed to remove stock from sector: {e}") from e

    async def remove_sector(self, sector_name):
        try:
            self._xtdata.remove_sector(sector_name)
        except Exception as e:
            raise AdapterError(f"Failed to remove sector: {e}") from e

    async def reset_sector(self, sector_name, stock_list):
        try:
            return self._xtdata.reset_sector(sector_name, stock_list)
        except Exception as e:
            raise AdapterError(f"Failed to reset sector: {e}") from e
```

- [ ] **Step 4: 添加 ETF/可转债方法**

```python
    # ---- ETF/可转债接口 (xtdata) ----

    async def get_cb_info(self, stock_code):
        try:
            return self._xtdata.get_cb_info(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get cb info: {e}") from e

    async def download_cb_data(self):
        try:
            self._xtdata.download_cb_data()
        except Exception as e:
            raise AdapterError(f"Failed to download cb data: {e}") from e

    async def get_ipo_info(self, start_time="", end_time=""):
        try:
            return self._xtdata.get_ipo_info(start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get ipo info: {e}") from e

    async def get_etf_info(self):
        try:
            return self._xtdata.get_etf_info()
        except Exception as e:
            raise AdapterError(f"Failed to get etf info: {e}") from e

    async def download_etf_info(self):
        try:
            self._xtdata.download_etf_info()
        except Exception as e:
            raise AdapterError(f"Failed to download etf info: {e}") from e
```

- [ ] **Step 5: 添加交易存根方法**

在文件末尾添加所有交易存根方法，每个都是 `raise NotImplementedError("xxx not yet implemented")`。

```python
    # ---- 交易存根 (XtTrader，待后续实现) ----

    async def order_stock(self, stock_code, order_type, volume, price_type, price, strategy_name="", order_remark=""):
        raise NotImplementedError("order_stock not yet implemented")

    async def order_stock_async(self, stock_code, order_type, volume, price_type, price, strategy_name="", order_remark=""):
        raise NotImplementedError("order_stock_async not yet implemented")

    async def cancel_order_stock(self, order_id):
        raise NotImplementedError("cancel_order_stock not yet implemented")

    async def cancel_order_stock_async(self, order_id):
        raise NotImplementedError("cancel_order_stock_async not yet implemented")

    async def query_stock_asset(self):
        raise NotImplementedError("query_stock_asset not yet implemented")

    async def query_stock_orders(self):
        raise NotImplementedError("query_stock_orders not yet implemented")

    async def query_stock_order(self, order_id):
        raise NotImplementedError("query_stock_order not yet implemented")

    async def query_stock_trades(self):
        raise NotImplementedError("query_stock_trades not yet implemented")

    async def query_stock_positions(self):
        raise NotImplementedError("query_stock_positions not yet implemented")

    async def query_stock_position(self, stock_code):
        raise NotImplementedError("query_stock_position not yet implemented")

    async def fund_transfer(self, transfer_direction, price):
        raise NotImplementedError("fund_transfer not yet implemented")

    async def query_credit_detail(self):
        raise NotImplementedError("query_credit_detail not yet implemented")

    async def query_stk_compacts(self):
        raise NotImplementedError("query_stk_compacts not yet implemented")

    async def query_credit_subjects(self):
        raise NotImplementedError("query_credit_subjects not yet implemented")

    async def query_credit_slo_code(self):
        raise NotImplementedError("query_credit_slo_code not yet implemented")

    async def query_credit_assure(self):
        raise NotImplementedError("query_credit_assure not yet implemented")

    async def query_account_infos(self):
        raise NotImplementedError("query_account_infos not yet implemented")

    async def query_account_status(self):
        raise NotImplementedError("query_account_status not yet implemented")

    async def query_new_purchase_limit(self):
        raise NotImplementedError("query_new_purchase_limit not yet implemented")

    async def query_ipo_data(self):
        raise NotImplementedError("query_ipo_data not yet implemented")

    async def query_com_fund(self):
        raise NotImplementedError("query_com_fund not yet implemented")

    async def query_com_position(self):
        raise NotImplementedError("query_com_position not yet implemented")
```

- [ ] **Step 6: Commit**

```bash
git add src/adapter/qmt/client.py
git commit -m "feat: add QMT adapter market data, sector, ETF methods and trading stubs"
```

---

## Task 3: 扩展 QMTMockAdapter

**Files:**
- Modify: `src/adapter/mock/qmt_mock.py`

- [ ] **Step 1: 添加行情数据 mock 方法**

每个方法返回合理的 mock 数据。读取方法返回随机/固定数据，下载方法 pass。包括：`get_local_data`, `get_full_tick`, `get_full_kline`, `get_divid_factors`, `download_history_data`, `download_history_data2`, `get_trading_dates`, `get_trading_calendar`, `get_holidays`, `download_holiday_data`, `get_period_list`

- [ ] **Step 2: 添加合约信息和财务 mock 方法**

`get_instrument_detail` 返回模拟合约信息字典，`get_instrument_type` 返回 `{"stock": True}` 等，`get_financial_data` 返回空字典，`download_financial_data` 和 `download_financial_data2` 为 pass。

- [ ] **Step 3: 添加板块管理 mock 方法**

`get_sector_list` 返回板块列表，`download_sector_data` pass，`get_index_weight` 返回权重字典，其余板块操作返回成功。

- [ ] **Step 4: 添加 ETF/可转债 mock 方法**

`get_cb_info` 返回模拟可转债信息，`get_ipo_info` 返回空列表，`get_etf_info` 返回空字典，下载方法 pass。

- [ ] **Step 5: Commit**

```bash
git add src/adapter/mock/qmt_mock.py
git commit -m "feat: add QMT mock adapter methods for all market data endpoints"
```

---

## Task 4: 创建 QMT 路由文件

**Files:**
- Rewrite: `qmt/routes/market.py`
- Create: `qmt/routes/stock.py`
- Create: `qmt/routes/financial.py`
- Create: `qmt/routes/sector.py`
- Create: `qmt/routes/etf.py`

- [ ] **Step 1: 重写 `qmt/routes/market.py`**

完整替换为 13 个端点。每个端点遵循 TDX 模式：模块文档字符串 → `_get_adapter()` → `router = APIRouter()` → 端点函数。

注意：此重写将 `/stocks` 端点重命名为 `/stock-list-in-sector`，属于破坏性变更（QMT 尚未上线，可接受）。

```python
"""QMT 行情数据 REST API 路由.

提供板块股票列表、历史行情、下载、交易日历等 HTTP 接口.
对应 QMT SDK: xtquant.xtdata
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


class DownloadHistoryDataRequest(BaseModel):
    stock_code: str
    period: str = "1d"
    start_time: str = ""
    end_time: str = ""
    incrementally: bool | None = None


class BatchDownloadRequest(BaseModel):
    stock_list: list[str]
    period: str = "1d"
    start_time: str = ""
    end_time: str = ""


# 1. GET /stock-list-in-sector
@router.get("/stock-list-in-sector")
async def get_stock_list_in_sector(
    sector: str = Query("沪深A股", description="板块名称"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        stocks = await adapter.get_stock_list_in_sector(sector)
        return {"stocks": stocks, "count": len(stocks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 2. GET /market-data
@router.get("/market-data")
async def get_market_data(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query("close", description="逗号分隔的字段名"),
    period: str = Query("1d", description="K线周期"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    dividend_type: str = Query("none", description="复权类型"),
    count: int = Query(-1, description="数据个数"),
    fill_data: bool = Query(True, description="是否填充空缺"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]
    try:
        data = await adapter.get_market_data(
            stock_list=stock_list, fields=field_list, period=period,
            start_time=start_time, end_time=end_time,
            dividend_type=dividend_type, count=count, fill_data=fill_data,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 3. GET /local-data
@router.get("/local-data")
async def get_local_data(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query("close", description="逗号分隔的字段名"),
    period: str = Query("1d", description="K线周期"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    dividend_type: str = Query("none", description="复权类型"),
    count: int = Query(-1, description="数据个数"),
    fill_data: bool = Query(True, description="是否填充空缺"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]
    try:
        data = await adapter.get_local_data(
            stock_list=stock_list, fields=field_list, period=period,
            start_time=start_time, end_time=end_time,
            dividend_type=dividend_type, count=count, fill_data=fill_data,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 4. GET /full-tick
@router.get("/full-tick")
async def get_full_tick(
    codes: str = Query(..., description="逗号分隔的代码或市场代码"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    code_list = [c.strip() for c in codes.split(",")]
    try:
        data = await adapter.get_full_tick(code_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 5. GET /full-kline
@router.get("/full-kline")
async def get_full_kline(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query("", description="逗号分隔的字段名"),
    period: str = Query("1m", description="K线周期"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(1, description="数据个数"),
    dividend_type: str = Query("none", description="复权类型"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")] if fields else None
    try:
        data = await adapter.get_full_kline(
            stock_list=stock_list, period=period, fields=field_list,
            start_time=start_time, end_time=end_time, count=count,
            dividend_type=dividend_type,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 6. GET /divid-factors
@router.get("/divid-factors")
async def get_divid_factors(
    stock_code: str = Query(..., description="股票代码"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_divid_factors(stock_code, start_time, end_time)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 7. POST /download-history-data
@router.post("/download-history-data")
async def download_history_data(request: DownloadHistoryDataRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_history_data(
            request.stock_code, request.period,
            request.start_time, request.end_time, request.incrementally,
        )
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 8. POST /download-history-data2
@router.post("/download-history-data2")
async def download_history_data2(request: BatchDownloadRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_history_data2(
            request.stock_list, request.period,
            request.start_time, request.end_time,
        )
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 9. GET /trading-dates
@router.get("/trading-dates")
async def get_trading_dates(
    market: str = Query("SH", description="市场代码"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(-1, description="数据个数"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_trading_dates(market, start_time, end_time, count)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 10. GET /trading-calendar
@router.get("/trading-calendar")
async def get_trading_calendar(
    market: str = Query("SH", description="市场代码"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_trading_calendar(market, start_time, end_time)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 11. GET /holidays
@router.get("/holidays")
async def get_holidays():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_holidays()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 12. POST /download-holiday-data
@router.post("/download-holiday-data")
async def download_holiday_data():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_holiday_data()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# 13. GET /period-list
@router.get("/period-list")
async def get_period_list():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_period_list()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 2: 创建 `qmt/routes/stock.py`**

```python
"""QMT 合约信息 REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_instrument_detail, get_instrument_type)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


@router.get("/instrument-detail")
async def get_instrument_detail(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
    iscomplete: bool = Query(False, description="是否返回完整字段"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_instrument_detail(stock_code, iscomplete)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/instrument-type")
async def get_instrument_type(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_instrument_type(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 3: 创建 `qmt/routes/financial.py`**

```python
"""QMT 财务数据 REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_financial_data, download_financial_data, download_financial_data2)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


class DownloadFinancialDataRequest(BaseModel):
    stock_list: list[str]
    table_list: list[str] | None = None


class DownloadFinancialData2Request(BaseModel):
    stock_list: list[str]
    table_list: list[str] | None = None
    start_time: str = ""
    end_time: str = ""


@router.get("/financial-data")
async def get_financial_data(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    tables: str = Query("Balance", description="逗号分隔的表名"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    report_type: str = Query("report_time", description="报表筛选方式"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    stock_list = [s.strip() for s in stocks.split(",")]
    table_list = [t.strip() for t in tables.split(",")]
    try:
        data = await adapter.get_financial_data(
            stock_list, table_list, start_time, end_time, report_type,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-financial-data")
async def download_financial_data(request: DownloadFinancialDataRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_financial_data(request.stock_list, request.table_list)
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-financial-data2")
async def download_financial_data2(request: DownloadFinancialData2Request):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_financial_data2(
            request.stock_list, request.table_list,
            request.start_time, request.end_time,
        )
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 4: 创建 `qmt/routes/sector.py`**

```python
"""QMT 板块管理 REST API 路由.

对应 QMT SDK: xtquant.xtdata (板块相关接口)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


class CreateSectorFolderRequest(BaseModel):
    parent_node: str = ""
    folder_name: str
    overwrite: bool = True

class CreateSectorRequest(BaseModel):
    parent_node: str = ""
    sector_name: str
    overwrite: bool = True

class StockListSectorRequest(BaseModel):
    sector_name: str
    stock_list: list[str]

class SectorNameRequest(BaseModel):
    sector_name: str

class ResetSectorRequest(BaseModel):
    sector_name: str
    stock_list: list[str]


@router.get("/sector-list")
async def get_sector_list():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_sector_list()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-sector-data")
async def download_sector_data():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_sector_data()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/index-weight")
async def get_index_weight(
    index_code: str = Query(..., description="指数代码"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_index_weight(index_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-index-weight")
async def download_index_weight():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_index_weight()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/create-sector-folder")
async def create_sector_folder(request: CreateSectorFolderRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.create_sector_folder(
            request.parent_node, request.folder_name, request.overwrite,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/create-sector")
async def create_sector(request: CreateSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.create_sector(
            request.parent_node, request.sector_name, request.overwrite,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/add-sector")
async def add_sector(request: StockListSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.add_sector(request.sector_name, request.stock_list)
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/remove-stock-from-sector")
async def remove_stock_from_sector(request: StockListSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.remove_stock_from_sector(request.sector_name, request.stock_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/remove-sector")
async def remove_sector(request: SectorNameRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.remove_sector(request.sector_name)
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/reset-sector")
async def reset_sector(request: ResetSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.reset_sector(request.sector_name, request.stock_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 5: 创建 `qmt/routes/etf.py`**

```python
"""QMT ETF/可转债/IPO REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_cb_info, download_cb_data, get_ipo_info, get_etf_info, download_etf_info)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


@router.get("/cb-info")
async def get_cb_info(
    stock_code: str = Query(..., description="可转债代码，如 113001.SH"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_cb_info(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-cb-data")
async def download_cb_data():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_cb_data()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ipo-info")
async def get_ipo_info(
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_ipo_info(start_time, end_time)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/etf-info")
async def get_etf_info():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_etf_info()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-etf-info")
async def download_etf_info():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_etf_info()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
```

- [ ] **Step 6: Commit**

```bash
git add qmt/routes/
git commit -m "feat: add QMT route files - market, stock, financial, sector, etf

BREAKING: /api/qmt/market/stocks renamed to /stock-list-in-sector"
```

---

## Task 5: 更新 QMT main.py 注册路由

**Files:**
- Modify: `qmt/main.py`

- [ ] **Step 1: 添加路由导入和注册**

将 `qmt/main.py` 末尾的路由注册部分从：

```python
from qmt.routes.market import router as market_router
from qmt.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/qmt", tags=["Market"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
```

改为：

```python
from qmt.routes.etf import router as etf_router
from qmt.routes.financial import router as financial_router
from qmt.routes.market import router as market_router
from qmt.routes.sector import router as sector_router
from qmt.routes.stock import router as stock_router
from qmt.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/qmt", tags=["Market"])
app.include_router(stock_router, prefix="/api/qmt", tags=["Stock"])
app.include_router(financial_router, prefix="/api/qmt", tags=["Financial"])
app.include_router(sector_router, prefix="/api/qmt", tags=["Sector"])
app.include_router(etf_router, prefix="/api/qmt", tags=["ETF"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
```

同时更新 app description。

- [ ] **Step 2: 启动服务验证路由注册**

```bash
uv run uvicorn qmt.main:app --port 9002 &
sleep 3
curl -s http://localhost:9002/health | python3 -m json.tool
curl -s http://localhost:9002/openapi.json | python3 -c "import sys,json; paths=json.load(sys.stdin)['paths']; print(f'Total endpoints: {len(paths)}'); [print(p) for p in sorted(paths)]"
kill %1
```

Expected: 34+ endpoints registered，包括 `/api/qmt/market/*`、`/api/qmt/stock/*`、`/api/qmt/financial/*`、`/api/qmt/sector/*`、`/api/qmt/etf/*`。

- [ ] **Step 3: Commit**

```bash
git add qmt/main.py
git commit -m "feat: register all QMT routes in main.py"
```

---

## Task 6: 修复测试 fixture 和编写集成测试

**Files:**
- Modify: `tests/conftest.py`
- Create: `tests/integration/test_qmt_routes.py`

- [ ] **Step 1: 修复 qmt_client fixture**

将 `tests/conftest.py` 中的 `qmt_client` fixture 从空初始化改为与 `tdx_client` 一致的模式：

```python
@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    import qmt.main
    from src.adapter import create_qmt_adapter

    qmt.main.qmt_adapter = create_qmt_adapter(
        path="", account_id=""
    )
    await qmt.main.qmt_adapter.initialize()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=qmt_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        if qmt.main.qmt_adapter:
            await qmt.main.qmt_adapter.shutdown()
            qmt.main.qmt_adapter = None
```

- [ ] **Step 2: 编写 QMT 路由集成测试**

创建 `tests/integration/test_qmt_routes.py`，为每个路由组编写测试类，测试所有端点返回 200 和正确的响应格式：

- `TestMarketRoutes`: 13 个端点测试
- `TestStockRoutes`: 2 个端点测试
- `TestFinancialRoutes`: 3 个端点测试
- `TestSectorRoutes`: 10 个端点测试
- `TestETFRoutes`: 5 个端点测试

- [ ] **Step 3: 运行测试**

```bash
uv run pytest tests/integration/test_qmt_routes.py -v
```

Expected: ALL PASS

- [ ] **Step 4: 运行全量测试确认无破坏**

```bash
uv run pytest tests/ -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add QMT route integration tests and fix qmt_client fixture"
```

---

## Task 7: 最终验证

- [ ] **Step 1: Lint 检查**

```bash
uv run ruff check .
```

Expected: 无错误

- [ ] **Step 2: 启动服务手动验证**

```bash
uv run uvicorn qmt.main:app --port 9002 --reload
```

在另一个终端验证关键端点：

```bash
curl http://localhost:9002/health
curl http://localhost:9002/api/qmt/market/stock-list-in-sector
curl http://localhost:9002/api/qmt/market/period-list
curl http://localhost:9002/api/qmt/stock/instrument-detail?stock_code=600000.SH
curl http://localhost:9002/api/qmt/financial/financial-data?stocks=600000.SH&tables=Balance
curl http://localhost:9002/api/qmt/sector/sector-list
curl http://localhost:9002/api/qmt/etf/cb-info?stock_code=113001.SH
curl http://localhost:9002/api/qmt/market/trading-calendar?market=SH
```

Expected: 所有请求返回 200 和 JSON 响应。

- [ ] **Step 3: 检查 OpenAPI 文档**

浏览器打开 `http://localhost:9002/docs`，确认所有端点正确显示。
