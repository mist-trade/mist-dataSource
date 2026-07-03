"""TDX 板块管理 REST API 路由.

提供板块列表、自定义板块管理等 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_sector_list, get_user_sector, create_sector 等)
"""

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from tdx.routes.dependencies import call_tdx_adapter, require_tdx_adapter

router = APIRouter()


class SectorRequest(BaseModel):
    """板块请求模型."""

    block_code: str = ""
    block_name: str = ""


@router.get("/sector-list")
async def get_sector_list(
    request: Request,
    list_type: int = Query(0, description="返回类型: 0=只返回代码, 1=返回代码和名称"),
):
    """获取A股板块代码列表.

    对应 TDX SDK: tq.get_sector_list(list_type)

    Returns:
        {"data": list}
    """
    adapter = require_tdx_adapter(request)

    data = await call_tdx_adapter(adapter.get_sector_list(list_type))
    return {"data": data}


@router.get("/user-sectors")
async def get_user_sectors(request: Request):
    """获取自定义板块列表.

    对应 TDX SDK: tq.get_user_sector()

    Returns:
        {"data": list}
    """
    adapter = require_tdx_adapter(request)

    data = await call_tdx_adapter(adapter.get_user_sector())
    return {"data": data}


@router.post("/create-sector")
async def create_sector(payload: SectorRequest, request: Request):
    """创建自定义板块.

    对应 TDX SDK: tq.create_sector(block_code, block_name)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    data = await call_tdx_adapter(adapter.create_sector(payload.block_code, payload.block_name))
    return {"data": data}


@router.post("/delete-sector")
async def delete_sector(payload: SectorRequest, request: Request):
    """删除自定义板块.

    对应 TDX SDK: tq.delete_sector(block_code)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    data = await call_tdx_adapter(adapter.delete_sector(payload.block_code))
    return {"data": data}


@router.post("/rename-sector")
async def rename_sector(payload: SectorRequest, request: Request):
    """重命名自定义板块.

    对应 TDX SDK: tq.rename_sector(block_code, block_name)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    data = await call_tdx_adapter(adapter.rename_sector(payload.block_code, payload.block_name))
    return {"data": data}


@router.post("/clear-sector")
async def clear_sector(payload: SectorRequest, request: Request):
    """清空自定义板块成份股.

    对应 TDX SDK: tq.clear_sector(block_code)

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_adapter(request)

    data = await call_tdx_adapter(adapter.clear_sector(payload.block_code))
    return {"data": data}


@router.post("/send-user-block")
async def send_user_block(payload: SectorRequest, request: Request):
    """发送自定义板块到通达信终端.

    对应 TDX SDK: tq.send_user_block(block_code, stocks)

    Note: 此接口需要额外的stocks参数，这里使用简化的SectorRequest模型.
    """
    adapter = require_tdx_adapter(request)

    # 注意：实际实现需要扩展请求模型以包含stocks列表
    data = await call_tdx_adapter(adapter.send_user_block(payload.block_code, []))
    return {"data": data}
