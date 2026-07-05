"""TDX 客户端控制 REST API 路由.

提供调用通达信客户端功能的 HTTP 接口.
对应 TDX SDK: tqcenter.tq (exec_to_tdx)
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tdx.routes.legacy.dependencies import call_tdx_legacy_adapter, require_tdx_legacy_adapter

router = APIRouter()


class ExecRequest(BaseModel):
    """执行命令请求模型."""

    cmd: str = ""
    param: str = ""


@router.post("/exec-to-tdx")
async def exec_to_tdx(payload: ExecRequest, request: Request):
    """调用客户端功能接口.

    对应 TDX SDK: tq.exec_to_tdx(cmd, param)

    此接口可以触发通达信客户端的各种功能，如打开股票图表等.

    Args:
        payload: 包含cmd和param的请求体

    Returns:
        {"data": dict}
    """
    adapter = require_tdx_legacy_adapter(request)

    data = await call_tdx_legacy_adapter(adapter.exec_to_tdx(payload.cmd, payload.param))
    return {"data": data}
