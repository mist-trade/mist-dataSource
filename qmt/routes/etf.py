"""QMT ETF/可转债/IPO REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_cb_info, download_cb_data, get_ipo_info, get_etf_info, download_etf_info)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


@router.get("/cb-info")
async def get_cb_info(
    stock_code: str = Query(..., description="可转债代码，如 113001.SH"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_cb_info(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-cb-data")
async def download_cb_data():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_cb_data()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/ipo-info")
async def get_ipo_info(
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_ipo_info(start_time, end_time)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/etf-info")
async def get_etf_info():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_etf_info()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-etf-info")
async def download_etf_info():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_etf_info()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
