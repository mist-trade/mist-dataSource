"""QMT 板块管理 REST API 路由.

对应 full-QMT bridge 板块命令。
"""

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from qmt.routes.dependencies import call_qmt_adapter, require_qmt_adapter

router = APIRouter()


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
async def get_sector_list(adapter: Any = Depends(require_qmt_adapter)):
    data = await call_qmt_adapter(adapter.get_sector_list())
    return {"data": data}


@router.post("/download-sector-data")
async def download_sector_data(adapter: Any = Depends(require_qmt_adapter)):
    await call_qmt_adapter(adapter.download_sector_data())
    return {"data": "ok"}


@router.get("/index-weight")
async def get_index_weight(
    index_code: str = Query(..., description="指数代码"),
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.get_index_weight(index_code))
    return {"data": data}


@router.post("/download-index-weight")
async def download_index_weight(adapter: Any = Depends(require_qmt_adapter)):
    await call_qmt_adapter(adapter.download_index_weight())
    return {"data": "ok"}


@router.post("/create-sector-folder")
async def create_sector_folder(
    request: CreateSectorFolderRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(
        adapter.create_sector_folder(request.parent_node, request.folder_name, request.overwrite)
    )
    return {"data": data}


@router.post("/create-sector")
async def create_sector(
    request: CreateSectorRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(
        adapter.create_sector(request.parent_node, request.sector_name, request.overwrite)
    )
    return {"data": data}


@router.post("/add-sector")
async def add_sector(
    request: StockListSectorRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    await call_qmt_adapter(adapter.add_sector(request.sector_name, request.stock_list))
    return {"data": "ok"}


@router.post("/remove-stock-from-sector")
async def remove_stock_from_sector(
    request: StockListSectorRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(
        adapter.remove_stock_from_sector(request.sector_name, request.stock_list)
    )
    return {"data": data}


@router.post("/remove-sector")
async def remove_sector(
    request: SectorNameRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    await call_qmt_adapter(adapter.remove_sector(request.sector_name))
    return {"data": "ok"}


@router.post("/reset-sector")
async def reset_sector(
    request: ResetSectorRequest,
    adapter: Any = Depends(require_qmt_adapter),
):
    data = await call_qmt_adapter(adapter.reset_sector(request.sector_name, request.stock_list))
    return {"data": data}
