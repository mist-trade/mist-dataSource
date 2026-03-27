"""Market data REST API routes for TDX adapter."""

from fastapi import APIRouter, HTTPException

from instance1.main import tdx_adapter

router = APIRouter()


@router.get("/stocks")
async def get_stock_list(sector: str = "通达信88"):
    """获取板块股票列表.

    Args:
        sector: 板块名称，默认 "通达信88"

    Returns:
        股票代码列表和数量
    """
    if not tdx_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stocks = await tdx_adapter.get_stock_list(sector)
    return {"stocks": stocks, "count": len(stocks)}


@router.get("/market-data")
async def get_market_data(
    stocks: str,  # 逗号分隔的股票代码
    fields: str = "Close",  # 逗号分隔的字段名
    period: str = "1d",
    start_time: str = "",
    end_time: str = "",
):
    """获取历史行情数据.

    Args:
        stocks: 股票代码列表，逗号分隔，如 "SH600519,SZ000001"
        fields: 字段列表，逗号分隔，如 "Close,Open,Volume"
        period: 周期，如 "1d", "1min", "5min"
        start_time: 开始时间，格式 "20240101"
        end_time: 结束时间，格式 "20241231"

    Returns:
        行情数据字典

    Raises:
        HTTPException: If adapter is not initialized or query fails
    """
    if not tdx_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    try:
        data = await tdx_adapter.get_market_data(
            stock_list=stock_list,
            fields=field_list,
            period=period,
            start_time=start_time,
            end_time=end_time,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
