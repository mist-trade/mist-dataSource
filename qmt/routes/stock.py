"""QMT 合约信息 REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_instrument_detail, get_instrument_type)
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from qmt.routes.dependencies import require_qmt_adapter

router = APIRouter()


@router.get("/instrument-detail")
async def get_instrument_detail(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
    iscomplete: bool = Query(False, description="是否返回完整字段"),
    adapter: Any = Depends(require_qmt_adapter),
):
    try:
        data = await adapter.get_instrument_detail(stock_code, iscomplete)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/instrument-type")
async def get_instrument_type(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
    adapter: Any = Depends(require_qmt_adapter),
):
    try:
        data = await adapter.get_instrument_type(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
