"""TDX 财务数据 REST API 路由.

提供专业财务数据查询的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_financial_data, get_financial_data_by_date, get_gp_one_data)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main
    return tdx.main.tdx_adapter


@router.get("/financial-data")
async def get_financial_data(
    stocks: str = Query(..., description="逗号分隔的股票代码，如 600519.SH,000001.SZ"),
    fields: str = Query(..., description="逗号分隔的字段名，如 FN193,FN194"),
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
    report_type: str = Query("announce_time", description="报表筛选方式: announce_time/report_time"),
):
    """获取专业财务数据.

    对应 TDX SDK: tq.get_financial_data(stock_list, field_list, start_time, end_time, report_type)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    try:
        data = await adapter.get_financial_data(stock_list, field_list, start_time, end_time, report_type)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/financial-data-by-date")
async def get_financial_data_by_date(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query(..., description="逗号分隔的字段名"),
    year: int = Query(..., description="年份，如 2024"),
    mmdd: int = Query(0, description="月日，如 1231 表示12月31日"),
):
    """获取指定日期专业财务数据.

    对应 TDX SDK: tq.get_financial_data_by_date(stock_list, field_list, year, mmdd)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    try:
        data = await adapter.get_financial_data_by_date(stock_list, field_list, year, mmdd)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/gp-one-data")
async def get_gp_one_data(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    fields: str = Query(..., description="逗号分隔的字段名"),
):
    """获取股票单个数据.

    对应 TDX SDK: tq.get_gp_one_data(stock_list, field_list)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    stock_list = [s.strip() for s in stocks.split(",")]
    field_list = [f.strip() for f in fields.split(",")]

    try:
        data = await adapter.get_gp_one_data(stock_list, field_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
