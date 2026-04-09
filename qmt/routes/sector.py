"""QMT 板块管理 REST API 路由.

对应 QMT SDK: xtquant.xtdata (板块相关接口)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    import qmt.main
    return qmt.main.qmt_adapter


class CreateSectorFolderRequest(BaseModel):
    parent_node: str = ""
    folder_name: str
    overwrite: bool = True


class CreateSectorRequest(BaseModel):
    parent_node: str = ""
    sector_name: str
    overwrite: bool = True


class StockListSectorRequest(BaseModel):
    sector_name: str
    stock_list: list[str]


class SectorNameRequest(BaseModel):
    sector_name: str


class ResetSectorRequest(BaseModel):
    sector_name: str
    stock_list: list[str]


@router.get("/sector-list")
async def get_sector_list():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_sector_list()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-sector-data")
async def download_sector_data():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_sector_data()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/index-weight")
async def get_index_weight(
    index_code: str = Query(..., description="指数代码"),
):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.get_index_weight(index_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/download-index-weight")
async def download_index_weight():
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.download_index_weight()
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/create-sector-folder")
async def create_sector_folder(request: CreateSectorFolderRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.create_sector_folder(
            request.parent_node, request.folder_name, request.overwrite,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/create-sector")
async def create_sector(request: CreateSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.create_sector(
            request.parent_node, request.sector_name, request.overwrite,
        )
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/add-sector")
async def add_sector(request: StockListSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.add_sector(request.sector_name, request.stock_list)
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/remove-stock-from-sector")
async def remove_stock_from_sector(request: StockListSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.remove_stock_from_sector(request.sector_name, request.stock_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/remove-sector")
async def remove_sector(request: SectorNameRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        await adapter.remove_sector(request.sector_name)
        return {"data": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/reset-sector")
async def reset_sector(request: ResetSectorRequest):
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    try:
        data = await adapter.reset_sector(request.sector_name, request.stock_list)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
