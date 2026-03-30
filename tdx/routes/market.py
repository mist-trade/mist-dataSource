"""TDX 行情数据 REST API 路由.

提供板块股票列表查询和历史行情数据获取的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_stock_list_in_sector, get_market_data)
"""

from fastapi import APIRouter, HTTPException

from tdx.main import tdx_adapter

router = APIRouter()


@router.get("/stocks")
async def get_stock_list(sector: str = "通达信88"):
    """获取板块股票列表.

    对应 TDX SDK: tq.get_stock_list_in_sector(sector)

    Args:
        sector: 板块名称，默认 "通达信88"

    Returns:
        包含以下字段的字典:
        - stocks (list[str]): 股票代码列表
        - count (int): 股票数量

    Raises:
        HTTPException: 503 - 适配器未初始化

    Examples:
        >>> GET /api/tdx/stocks?sector=通达信88
        {"stocks": ["SH600519", "SZ000001", ...], "count": 88}
    """
    if not tdx_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stocks = await tdx_adapter.get_stock_list(sector)
    return {"stocks": stocks, "count": len(stocks)}


@router.get("/market-data")
async def get_market_data(
    stocks: str,
    fields: str = "Close",
    period: str = "1d",
    start_time: str = "",
    end_time: str = "",
):
    """获取历史行情数据.

    对应 TDX SDK: tq.get_market_data(field_list, stock_list, period, start_time, end_time, ...)

    支持的字段: Date, Time, Open, High, Low, Close, Volume, Amount, ForwardFactor.
    支持的周期: "1d"(日线), "1m"(分钟线), "5m"(五分钟线).

    Args:
        stocks: 股票代码列表，逗号分隔，如 "SH600519,SZ000001"
        fields: 字段列表，逗号分隔，如 "Close,Open,Volume"，默认 "Close"
        period: K线周期，支持 "1d", "1m", "5m"，默认 "1d"
        start_time: 开始时间，格式 "YYYYMMDD"，如 "20240101"，空字符串表示不限制
        end_time: 结束时间，格式 "YYYYMMDD"，如 "20241231"，空字符串表示不限制

    Returns:
        包含以下字段的字典:
        - data (dict[str, Any]): 行情数据，key 为字段名，value 为 {股票代码: 数据值}

    Raises:
        HTTPException: 503 - 适配器未初始化; 500 - 查询失败

    Examples:
        >>> GET /api/tdx/market-data?stocks=SH600519&fields=Close,Volume&period=1d&start_time=20240101
        {"data": {"Close": {"SH600519": 1680.50}, "Volume": {"SH600519": 25000}}}
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
