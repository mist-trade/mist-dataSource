"""TDX ETF/债券 REST API 路由.

提供可转债、新股申购、ETF等信息查询的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_kzz_info, get_ipo_info, get_trackzs_etf_info)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main
    return tdx.main.tdx_adapter


@router.get("/kzz-info")
async def get_kzz_info(
    stock_code: str = Query(..., description="可转债代码，如 113001.SH"),
    fields: str = Query("", description="逗号分隔的字段名"),
):
    """获取可转债信息.

    对应 TDX SDK: tq.get_kzz_info(stock_code, field_list)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    field_list = [f.strip() for f in fields.split(",")] if fields else []

    try:
        data = await adapter.get_kzz_info(stock_code, field_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ipo-info")
async def get_ipo_info(
    ipo_type: int = Query(0, description="IPO类型"),
    ipo_date: int = Query(0, description="IPO日期，格式 YYYYMMDD"),
):
    """获取新股申购信息.

    对应 TDX SDK: tq.get_ipo_info(ipo_type, ipo_date)

    Returns:
        {"data": list[dict]}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_ipo_info(ipo_type, ipo_date)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/trackzs-etf-info")
async def get_trackzs_etf_info(
    zs_code: str = Query(..., description="指数代码，如 000001.SH"),
):
    """获取跟踪指数的ETF信息.

    对应 TDX SDK: tq.get_trackzs_etf_info(zs_code)

    Returns:
        {"data": list[dict]}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_trackzs_etf_info(zs_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
