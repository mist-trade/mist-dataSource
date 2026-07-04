"""QMT 合约信息 REST API 路由.

对应 full-QMT bridge 合约信息命令。
"""

from typing import Any

from fastapi import APIRouter, Depends, Query

from qmt.routes.dependencies import call_qmt_adapter, require_qmt_adapter

router = APIRouter()


@router.get("/instrument-detail")
async def get_instrument_detail(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
    iscomplete: bool = Query(False, description="是否返回完整字段"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_instrument_detail(stock_code, iscomplete))
    return {"data": data}


@router.get("/instrument-type")
async def get_instrument_type(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_instrument_type(stock_code))
    return {"data": data}
