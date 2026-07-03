"""TDX 交易数据 REST API 路由.

提供板块、股票、市场交易数据查询的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_bkjy_value, get_gpjy_value, get_scjy_value 等)
"""

from fastapi import APIRouter, Query, Request

from tdx.routes.dependencies import call_tdx_adapter, require_tdx_adapter

router = APIRouter()


@router.get("/bkjy-value")
async def get_bkjy_value(
    request: Request,
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query(..., description="逗号分隔的字段名"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
):
    """获取板块交易数据.

    对应 TDX SDK: tq.get_bkjy_value(stock_list, field_list, start_time, end_time)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    data = await call_tdx_adapter(
        adapter.get_bkjy_value(stock_list, field_list, start_time, end_time)
    )
    return {"data": data}


@router.get("/bkjy-value-by-date")
async def get_bkjy_value_by_date(
    request: Request,
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query(..., description="逗号分隔的字段名"),
    year: int = Query(..., description="年份"),
    mmdd: int = Query(0, description="月日"),
):
    """获取指定日期板块交易数据.

    对应 TDX SDK: tq.get_bkjy_value_by_date(stock_list, field_list, year, mmdd)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    data = await call_tdx_adapter(
        adapter.get_bkjy_value_by_date(stock_list, field_list, year, mmdd)
    )
    return {"data": data}


@router.get("/gpjy-value")
async def get_gpjy_value(
    request: Request,
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query(..., description="逗号分隔的字段名"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
):
    """获取股票交易数据.

    对应 TDX SDK: tq.get_gpjy_value(stock_list, field_list, start_time, end_time)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    data = await call_tdx_adapter(
        adapter.get_gpjy_value(stock_list, field_list, start_time, end_time)
    )
    return {"data": data}


@router.get("/gpjy-value-by-date")
async def get_gpjy_value_by_date(
    request: Request,
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query(..., description="逗号分隔的字段名"),
    year: int = Query(..., description="年份"),
    mmdd: int = Query(0, description="月日"),
):
    """获取指定日期股票交易数据.

    对应 TDX SDK: tq.get_gpjy_value_by_date(stock_list, field_list, year, mmdd)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    data = await call_tdx_adapter(
        adapter.get_gpjy_value_by_date(stock_list, field_list, year, mmdd)
    )
    return {"data": data}


@router.get("/scjy-value")
async def get_scjy_value(
    request: Request,
    fields: str = Query(..., description="逗号分隔的字段名"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
):
    """获取市场交易数据.

    对应 TDX SDK: tq.get_scjy_value(field_list, start_time, end_time)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    field_list = [f.strip() for f in fields.split(",")]

    data = await call_tdx_adapter(adapter.get_scjy_value(field_list, start_time, end_time))
    return {"data": data}


@router.get("/scjy-value-by-date")
async def get_scjy_value_by_date(
    request: Request,
    fields: str = Query(..., description="逗号分隔的字段名"),
    year: int = Query(..., description="年份"),
    mmdd: int = Query(0, description="月日"),
):
    """获取指定日期市场交易数据.

    对应 TDX SDK: tq.get_scjy_value_by_date(field_list, year, mmdd)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    field_list = [f.strip() for f in fields.split(",")]

    data = await call_tdx_adapter(adapter.get_scjy_value_by_date(field_list, year, mmdd))
    return {"data": data}
