"""TDX 行情数据 REST API 路由.

提供板块股票列表查询和历史行情数据获取的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_stock_list_in_sector, get_market_data)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main
    return tdx.main.tdx_adapter


@router.get("/stock-list-in-sector")
async def get_stock_list_in_sector(
    block_code: str = Query("通达信88", description="板块代码或名称"),
    block_type: int = Query(0, description="板块类型: 0=板块指数代码/名称, 1=自定义板块代码"),
    list_type: int = Query(0, description="返回类型: 0=只返回代码, 1=返回代码和名称"),
):
    """获取板块股票列表.

    对应 TDX SDK: tq.get_stock_list_in_sector(block_code, block_type, list_type)

    Args:
        block_code: 板块代码或名称，默认 "通达信88"
        block_type: 板块类型，默认 0
        list_type: 返回类型，默认 0

    Returns:
        {"stocks": [...], "count": int}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stocks = await adapter.get_stock_list_in_sector(block_code, block_type, list_type)
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
    adapter = _get_adapter()
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


@router.get("/market-snapshot")
async def get_market_snapshot(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
    fields: str = Query("", description="逗号分隔的字段名，留空返回所有字段"),
):
    """获取实时行情快照.

    对应 TDX SDK: tq.get_market_snapshot(stock_code, field_list)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    field_list = [f.strip() for f in fields.split(",")] if fields else []

    try:
        data = await adapter.get_market_snapshot(stock_code, field_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/trading-dates")
async def get_trading_dates(
    market: str = Query("SH", description="市场代码: SH/SZ"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
    count: int = Query(-1, description="返回数据个数，-1表示全部"),
):
    """获取交易日列表.

    对应 TDX SDK: tq.get_trading_dates(market, start_time, end_time, count)

    Returns:
        {"data": list[str]}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_trading_dates(market, start_time, end_time, count)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/divid-factors")
async def get_divid_factors(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
):
    """获取除权除息数据.

    对应 TDX SDK: tq.get_divid_factors(stock_code, start_time, end_time)

    Returns:
        {"data": Any}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_divid_factors(stock_code, start_time, end_time)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/gb-info")
async def get_gb_info(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
    date_list: str = Query("", description="逗号分隔的日期列表，格式 YYYYMMDD"),
    count: int = Query(1, description="返回数据个数"),
):
    """获取股本数据.

    对应 TDX SDK: tq.get_gb_info(stock_code, date_list, count)

    Returns:
        {"data": list[dict]}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    dates = [d.strip() for d in date_list.split(",")] if date_list else []

    try:
        data = await adapter.get_gb_info(stock_code, dates, count)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/refresh-cache")
async def refresh_cache(
    market: str = Query("AG", description="市场代码"),
    force: bool = Query(False, description="是否强制刷新"),
):
    """刷新行情缓存.

    对应 TDX SDK: tq.refresh_cache(market, force)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.refresh_cache(market, force)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/refresh-kline")
async def refresh_kline(
    stock_list: str = Query("", description="逗号分隔的股票代码"),
    period: str = Query("1d", description="K线周期: 1d,1m,5m,15m,30m,60m"),
):
    """刷新K线缓存.

    对应 TDX SDK: tq.refresh_kline(stock_list, period)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stocks = [s.strip() for s in stock_list.split(",")] if stock_list else []

    try:
        data = await adapter.refresh_kline(stocks, period)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-file")
async def download_file(
    stock_code: str = Query("", description="股票代码"),
    down_time: str = Query("", description="下载时间，格式 YYYYMMDD"),
    down_type: int = Query(1, description="下载类型"),
):
    """下载特定数据文件.

    对应 TDX SDK: tq.download_file(stock_code, down_time, down_type)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.download_file(stock_code, down_time, down_type)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
