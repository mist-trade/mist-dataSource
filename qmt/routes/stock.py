"""QMT 合约信息 REST API 路由.

对应 QMT SDK: xtquant.xtdata (get_instrument_detail, get_instrument_type)
"""

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


@router.get("/instrument-detail")
async def get_instrument_detail(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
    iscomplete: bool = Query(False, description="是否返回完整字段"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_instrument_detail(stock_code, iscomplete)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/instrument-type")
async def get_instrument_type(
    stock_code: str = Query(..., description="合约代码，如 600000.SH"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_instrument_type(stock_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
