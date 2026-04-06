"""TDX 板块管理 REST API 路由.

提供板块列表、自定义板块管理等 HTTP 接口.
对应 TDX SDK: tqcenter.tq (get_sector_list, get_user_sector, create_sector 等)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main
    return tdx.main.tdx_adapter


class SectorRequest(BaseModel):
    """板块请求模型."""
    block_code: str = ""
    block_name: str = ""


@router.get("/sector-list")
async def get_sector_list(
    list_type: int = Query(0, description="返回类型: 0=只返回代码, 1=返回代码和名称"),
):
    """获取A股板块代码列表.

    对应 TDX SDK: tq.get_sector_list(list_type)

    Returns:
        {"data": list}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_sector_list(list_type)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/user-sectors")
async def get_user_sectors():
    """获取自定义板块列表.

    对应 TDX SDK: tq.get_user_sector()

    Returns:
        {"data": list}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.get_user_sector()
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/create-sector")
async def create_sector(request: SectorRequest):
    """创建自定义板块.

    对应 TDX SDK: tq.create_sector(block_code, block_name)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.create_sector(request.block_code, request.block_name)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/delete-sector")
async def delete_sector(request: SectorRequest):
    """删除自定义板块.

    对应 TDX SDK: tq.delete_sector(block_code)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.delete_sector(request.block_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/rename-sector")
async def rename_sector(request: SectorRequest):
    """重命名自定义板块.

    对应 TDX SDK: tq.rename_sector(block_code, block_name)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.rename_sector(request.block_code, request.block_name)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/clear-sector")
async def clear_sector(request: SectorRequest):
    """清空自定义板块成份股.

    对应 TDX SDK: tq.clear_sector(block_code)

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.clear_sector(request.block_code)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/send-user-block")
async def send_user_block(request: SectorRequest):
    """发送自定义板块到通达信终端.

    对应 TDX SDK: tq.send_user_block(block_code, stocks)

    Note: 此接口需要额外的stocks参数，这里使用简化的SectorRequest模型.
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        # 注意：实际实现需要扩展请求模型以包含stocks列表
        data = await adapter.send_user_block(request.block_code, [])
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
