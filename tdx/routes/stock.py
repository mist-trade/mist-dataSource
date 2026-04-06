"""TDX 股票信息 REST API 路由.

提供股票基本信息、报告数据等查询的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_stock_info, get_report_data, get_more_info, get_relation)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main
    return tdx.main.tdx_adapter


@router.get("/stock-list")
async def get_stock_list(
    market: str = Query("0", description="市场代码: 0=深证A股, 1=上证A股, 2=深证B股, 3=上证B股"),
):
    """获取指定市场股票列表.

    对应 TDX SDK: tq.get_stock_list(market)

    Args:
        market: 市场代码，默认 "0"

    Returns:
        {"stocks": [...], "count": int}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        stocks = await adapter.get_stock_list(market)
        return {"stocks": stocks, "count": len(stocks)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/stock-info")
async def get_stock_info(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
):
    """获取股票基本信息.

    对应 TDX SDK: tq.get_stock_info(stock_code)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_stock_info(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/report-data")
async def get_report_data(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
):
    """获取报告数据.

    对应 TDX SDK: tq.get_report_data(stock_code)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_report_data(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/more-info")
async def get_more_info(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
    fields: str = Query("", description="逗号分隔的字段名"),
):
    """获取更多信息.

    对应 TDX SDK: tq.get_more_info(stock_code, field_list)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    field_list = [f.strip() for f in fields.split(",")] if fields else []

    try:
        data = await adapter.get_more_info(stock_code, field_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/relation")
async def get_relation(
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
):
    """获取股票所属板块.

    对应 TDX SDK: tq.get_relation(stock_code)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_relation(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
