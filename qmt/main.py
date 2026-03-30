"""QMT 适配器 FastAPI 应用入口 (Port 9002).

启动方式: uvicorn qmt.main:app --port 9002 --reload
对应 QMT SDK: xtquant.xtdata (行情)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapter import create_qmt_adapter
from src.adapter.base import MarketDataAdapter
from src.core.config import settings
from src.core.logging import setup_logging
from src.ws.manager import ConnectionManager

setup_logging()

qmt_adapter: MarketDataAdapter | None = None
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理器.

    启动时创建并初始化 QMT 适配器，关闭时执行清理.
    对应 QMT SDK: xtdata 连接 MiniQMT 客户端

    Args:
        app: FastAPI 应用实例

    Yields:
        None
    """
    global qmt_adapter
    qmt_adapter = create_qmt_adapter(
        path=settings.qmt.path, account_id=settings.qmt.account_id
    )
    await qmt_adapter.initialize()
    yield
    if qmt_adapter:
        await qmt_adapter.shutdown()


app = FastAPI(
    title="Mist DataSource - QMT Adapter",
    description="miniQMT 数据源适配器 - 提供行情接口",
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
        - instance (str): 实例标识，固定为 "qmt"
        - adapter (str): 当前适配器类名，未初始化时为 "none"
        - connections (int): 当前 WebSocket 连接数

    Examples:
        >>> GET /health
        {"status": "ok", "instance": "qmt", "adapter": "QMTMockAdapter", "connections": 0}
    """
    return {
        "status": "ok",
        "instance": "qmt",
        "adapter": type(qmt_adapter).__name__ if qmt_adapter else "none",
        "connections": ws_manager.connection_count,
    }


from qmt.routes.market import router as market_router
from qmt.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/qmt", tags=["Market"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
