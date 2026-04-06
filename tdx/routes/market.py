"""TDX 行情数据 REST API 路由.

提供板块股票列表查询和历史行情数据获取的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_stock_list_in_sector, get_market_data)
"""

from fastapi import APIRouter, HTTPException, Query

import tdx.main

router = APIRouter()


@router.get("/stocks")
async def get_stock_list(sector: str = "通达信88"):
    """获取板块股票列表.

    对应 TDX SDK: tq.get_stock_list_in_sector(sector)

    Args:
        sector: 板块名称，默认 "通达信88"

    Returns:
        {"stocks": [...], "count": int}
    """
    adapter = tdx.main.tdx_adapter
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stocks = await adapter.get_stock_list(sector)
    return {"stocks": stocks, "count": len(stocks)}


@router.get("/market-data")
async def get_market_data(
    stocks: str = Query(..., description="逗号分隔的股票代码，如 SH600519,SZ000001"),
    fields: str = Query("Close", description="逗号分隔的字段名，如 Close,Open,Volume"),
    period: str = Query("1d", description="K线周期: 1d,1m,5m"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
    dividend_type: str = Query("front", description="复权类型: front,none,back"),
):
    """获取历史行情数据.

    对应 TDX SDK: tq.get_market_data(field_list, stock_list, period, start_time, end_time, ...)

    支持的字段: Date, Time, Open, High, Low, Close, Volume, Amount, ForwardFactor.
    支持的周期: "1d"(日线), "1m"(分钟线), "5m"(五分钟线).

    Returns:
        {"data": dict}
    """
    adapter = tdx.main.tdx_adapter
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    try:
        data = await adapter.get_market_data(
            stock_list=stock_list,
            fields=field_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
            dividend_type=dividend_type,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
