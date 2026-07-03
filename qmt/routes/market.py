"""QMT 行情数据 REST API 路由.

提供板块股票列表、历史行情、下载、交易日历等 HTTP 接口.
对应 QMT SDK: xtquant.xtdata
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from qmt.routes.dependencies import call_qmt_adapter, require_qmt_adapter

router = APIRouter()


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
    adapter: Any = Depends(require_qmt_adapter),
):
    stocks = await call_qmt_adapter(adapter.get_stock_list_in_sector(sector))
    return {"stocks": stocks, "count": len(stocks)}


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
    adapter: Any = Depends(require_qmt_adapter),
):
    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]
    data = await call_qmt_adapter(
        adapter.get_market_data(
            stock_list=stock_list,
            fields=field_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
            dividend_type=dividend_type,
            count=count,
            fill_data=fill_data,
        )
    )
    return {"data": data}


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
    adapter: Any = Depends(require_qmt_adapter),
):
    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]
    data = await call_qmt_adapter(
        adapter.get_local_data(
            stock_list=stock_list,
            fields=field_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
            dividend_type=dividend_type,
            count=count,
            fill_data=fill_data,
        )
    )
    return {"data": data}


# 4. GET /full-tick
@router.get("/full-tick")
async def get_full_tick(
    codes: str = Query(..., description="逗号分隔的代码或市场代码"),
    adapter: Any = Depends(require_qmt_adapter),
):
    code_list = [c.strip() for c in codes.split(",")]
    data = await call_qmt_adapter(adapter.get_full_tick(code_list))
    return {"data": data}


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
    adapter: Any = Depends(require_qmt_adapter),
):
    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")] if fields else None
    data = await call_qmt_adapter(
        adapter.get_full_kline(
            stock_list=stock_list,
            period=period,
            fields=field_list,
            start_time=start_time,
            end_time=end_time,
            count=count,
            dividend_type=dividend_type,
        )
    )
    return {"data": data}


# 6. GET /divid-factors
@router.get("/divid-factors")
async def get_divid_factors(
    stock_code: str = Query(..., description="股票代码"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_divid_factors(stock_code, start_time, end_time))
    return {"data": data}


# 7. POST /download-history-data
@router.post("/download-history-data")
async def download_history_data(
    request: DownloadHistoryDataRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    await call_qmt_adapter(
        adapter.download_history_data(
            request.stock_code,
            request.period,
            request.start_time,
            request.end_time,
            request.incrementally,
        )
    )
    return {"data": "ok"}


# 8. POST /download-history-data2
@router.post("/download-history-data2")
async def download_history_data2(
    request: BatchDownloadRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    await call_qmt_adapter(
        adapter.download_history_data2(
            request.stock_list,
            request.period,
            request.start_time,
            request.end_time,
        )
    )
    return {"data": "ok"}


# 9. GET /trading-dates
@router.get("/trading-dates")
async def get_trading_dates(
    market: str = Query("SH", description="市场代码"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    count: int = Query(-1, description="数据个数"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_trading_dates(market, start_time, end_time, count))
    return {"data": data}


# 10. GET /trading-calendar
@router.get("/trading-calendar")
async def get_trading_calendar(
    market: str = Query("SH", description="市场代码"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_trading_calendar(market, start_time, end_time))
    return {"data": data}


# 11. GET /holidays
@router.get("/holidays")
async def get_holidays(adapter: Any = Depends(require_qmt_adapter)):
    data = await call_qmt_adapter(adapter.get_holidays())
    return {"data": data}


# 12. POST /download-holiday-data
@router.post("/download-holiday-data")
async def download_holiday_data(adapter: Any = Depends(require_qmt_adapter)):
    await call_qmt_adapter(adapter.download_holiday_data())
    return {"data": "ok"}


# 13. GET /period-list
@router.get("/period-list")
async def get_period_list(adapter: Any = Depends(require_qmt_adapter)):
    data = await call_qmt_adapter(adapter.get_period_list())
    return {"data": data}
