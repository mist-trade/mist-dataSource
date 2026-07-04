"""QMT ETF/可转债/IPO REST API 路由.

对应 full-QMT bridge 参考数据命令。
"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from qmt.routes.dependencies import call_qmt_adapter, require_qmt_adapter

router = APIRouter()


@router.get("/cb-info")
async def get_cb_info(
    stock_code: str = Query(..., description="可转债代码，如 113001.SH"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_cb_info(stock_code))
    return {"data": data}


@router.post("/download-cb-data")
async def download_cb_data(adapter: Any = Depends(require_qmt_adapter)):
    await call_qmt_adapter(adapter.download_cb_data())
    return {"data": "ok"}


@router.get("/ipo-info")
async def get_ipo_info(
    start_time: str = Query("", description="起始时间，格式 YYYYMMDD"),
    end_time: str = Query("", description="结束时间，格式 YYYYMMDD"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_ipo_info(start_time, end_time))
    return {"data": data}


@router.get("/etf-info")
async def get_etf_info(adapter: Any = Depends(require_qmt_adapter)):
    data = await call_qmt_adapter(adapter.get_etf_info())
    return {"data": data}


@router.post("/download-etf-info")
async def download_etf_info(adapter: Any = Depends(require_qmt_adapter)):
    await call_qmt_adapter(adapter.download_etf_info())
    return {"data": "ok"}
