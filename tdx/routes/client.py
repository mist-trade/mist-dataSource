"""TDX 客户端控制 REST API 路由.

提供调用通达信客户端功能的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (exec_to_tdx)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


def _get_adapter():
    """获取 TDX 适配器实例.

    延迟导入避免循环依赖.
    """
    import tdx.main
    return tdx.main.tdx_adapter


class ExecRequest(BaseModel):
    """执行命令请求模型."""
    cmd: str = ""
    param: str = ""


@router.post("/exec-to-tdx")
async def exec_to_tdx(request: ExecRequest):
    """调用客户端功能接口.

    对应 TDX SDK: tq.exec_to_tdx(cmd, param)

    此接口可以触发通达信客户端的各种功能，如打开股票图表等.

    Args:
        request: 包含cmd和param的请求体

    Returns:
        {"data": dict}
    """
    adapter = _get_adapter()
    if not adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        data = await adapter.exec_to_tdx(request.cmd, request.param)
        return {"data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
