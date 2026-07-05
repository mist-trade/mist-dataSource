"""TDX 股票信息 REST API 路由.

提供股票基本信息等查询的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_stock_info, get_more_info, get_relation)
"""

from fastapi import APIRouter, Query, Request

from tdx.routes.legacy.dependencies import call_tdx_legacy_adapter, require_tdx_legacy_adapter

router = APIRouter()


@router.get("/stock-list")
async def get_stock_list(
    request: Request,
    market: str = Query("0", description="市场代码: 0=深证A股, 1=上证A股, 2=深证B股, 3=上证B股"),
):
    """获取指定市场股票列表.

    对应 TDX SDK: tq.get_stock_list(market)

    Args:
        market: 市场代码，默认 "0"

    Returns:
        {"stocks": [...], "count": int}
    """
    adapter = require_tdx_legacy_adapter(request)

    stocks = await call_tdx_legacy_adapter(adapter.get_stock_list(market))
    return {"stocks": stocks, "count": len(stocks)}


@router.get("/stock-info")
async def get_stock_info(
    request: Request,
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
):
    """获取股票基本信息.

    对应 TDX SDK: tq.get_stock_info(stock_code)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_legacy_adapter(request)

    data = await call_tdx_legacy_adapter(adapter.get_stock_info(stock_code))
    return {"data": data}


@router.get("/more-info")
async def get_more_info(
    request: Request,
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
    fields: str = Query("", description="逗号分隔的字段名"),
):
    """获取更多信息.

    对应 TDX SDK: tq.get_more_info(stock_code, field_list)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_legacy_adapter(request)

    field_list = [f.strip() for f in fields.split(",")] if fields else []

    data = await call_tdx_legacy_adapter(adapter.get_more_info(stock_code, field_list))
    return {"data": data}


@router.get("/relation")
async def get_relation(
    request: Request,
    stock_code: str = Query(..., description="股票代码，如 600519.SH"),
):
    """获取股票所属板块.

    对应 TDX SDK: tq.get_relation(stock_code)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_legacy_adapter(request)

    data = await call_tdx_legacy_adapter(adapter.get_relation(stock_code))
    return {"data": data}
