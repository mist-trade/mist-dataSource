"""QMT 财务数据 REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_financial_data, download_financial_data, download_financial_data2)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


class DownloadFinancialDataRequest(BaseModel):
    stock_list: list[str]
    table_list: list[str] | None = None


class DownloadFinancialData2Request(BaseModel):
    stock_list: list[str]
    table_list: list[str] | None = None
    start_time: str = ""
    end_time: str = ""


@router.get("/financial-data")
async def get_financial_data(
    stocks: str = Query(..., description="逗号分隔的股票代码"),
    tables: str = Query("Balance", description="逗号分隔的表名"),
    start_time: str = Query("", description="起始时间"),
    end_time: str = Query("", description="结束时间"),
    report_type: str = Query("report_time", description="报表筛选方式"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    stock_list = [s.strip() for s in stocks.split(",")]
    table_list = [t.strip() for t in tables.split(",")]
    try:
        data = await adapter.get_financial_data(
            stock_list, table_list, start_time, end_time, report_type,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-financial-data")
async def download_financial_data(request: DownloadFinancialDataRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_financial_data(request.stock_list, request.table_list)
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-financial-data2")
async def download_financial_data2(request: DownloadFinancialData2Request):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_financial_data2(
            request.stock_list, request.table_list,
            request.start_time, request.end_time,
        )
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
