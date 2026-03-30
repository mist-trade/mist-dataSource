"""TDX 适配器 FastAPI 应用入口 (Port 9001).

启动方式: uvicorn tdx.main:app --port 9001 --reload
对应 TDX SDK: tqcenter.tq (通过 MarketDataAdapter 适配器层调用)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapter import create_tdx_adapter
from src.adapter.base import MarketDataAdapter
from src.core.config import settings
from src.core.logging import setup_logging
from src.ws.manager import ConnectionManager

setup_logging()

tdx_adapter: MarketDataAdapter | None = None
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器.

    启动时创建并初始化 TDX 适配器，关闭时执行清理.
    对应 TDX SDK: tq.initialize(__file__)

    Args:
        app: FastAPI 应用实例

    Yields:
        None
    """
    global tdx_adapter
    tdx_adapter = create_tdx_adapter()
    await tdx_adapter.initialize()
    yield
    if tdx_adapter:
        await tdx_adapter.shutdown()


app = FastAPI(
    title="Mist DataSource - TDX Adapter",
    description="通达信数据源适配器 - 提供 HTTP/WebSocket 接口",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """健康检查端点.

    Returns:
        包含以下字段的字典:
        - status (str): 服务状态，固定为 "ok"
        - instance (str): 实例标识，固定为 "tdx"
        - adapter (str): 当前适配器类名，未初始化时为 "none"
        - connections (int): 当前 WebSocket 连接数

    Examples:
        >>> GET /health
        {"status": "ok", "instance": "tdx", "adapter": "TDXMockAdapter", "connections": 0}
    """
    return {
        "status": "ok",
        "instance": "tdx",
        "adapter": type(tdx_adapter).__name__ if tdx_adapter else "none",
        "connections": ws_manager.connection_count,
    }


from tdx.routes.market import router as market_router
from tdx.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/tdx", tags=["Market"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
