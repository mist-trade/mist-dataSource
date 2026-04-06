"""QMT 行情数据 REST API 路由.

提供板块股票列表查询和历史行情数据获取的 HTTP 接口.
对应 QMT SDK: xtquant.xtdata (get_stock_list_in_sector, get_market_data)
"""

from fastapi import APIRouter, HTTPException, Query

import qmt.main

router = APIRouter()


@router.get("/stocks")
async def get_stock_list(sector: str = "沪深300"):
    """获取板块股票列表.

    对应 QMT SDK: xtdata.get_stock_list_in_sector(sector_name)

    Args:
        sector: 板块名称，默认 "沪深300"

    Returns:
        {"stocks": [...], "count": int}
    """
    adapter = qmt.main.qmt_adapter
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stocks = await adapter.get_stock_list(sector)
    return {"stocks": stocks, "count": len(stocks)}


@router.get("/market-data")
async def get_market_data(
    stocks: str = Query(..., description="逗号分隔的股票代码，如 000001.SZ,600000.SH"),
    fields: str = Query("close", description="逗号分隔的字段名，如 close,open,volume"),
    period: str = Query("1d", description="K线周期: tick,1m,5m,15m,30m,1h,1d,1w,1mon"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
    dividend_type: str = Query("none", description="除权方式: none,front,back,front_ratio,back_ratio"),
):
    """获取历史行情数据.

    对应 QMT SDK: xtdata.get_market_data(field_list, stock_list, period, ...)

    支持的字段: time,open,high,low,close,volume,amount,settelementPrice,openInterest,preClose,suspendFlag.
    支持的周期: "tick","1m","5m","15m","30m","1h","1d","1w","1mon","1q","1hy","1y".

    Returns:
        {"data": dict}
    """
    adapter = qmt.main.qmt_adapter
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
