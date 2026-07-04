"""QMT 适配器 FastAPI 应用入口 (Port 9002).

启动方式: uvicorn qmt.main:app --port 9002 --reload
生产 QMT 接入通过大 QMT 内置 Python bridge；本 app 当前保留为 mock/diagnostic surface。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qmt.routes.bridge import router as bridge_router
from qmt.routes.etf import router as etf_router
from qmt.routes.financial import router as financial_router
from qmt.routes.market import router as market_router
from qmt.routes.sector import router as sector_router
from qmt.routes.stock import router as stock_router
from qmt.routes.ws import router as ws_router
from src.adapter import create_qmt_adapter
from src.adapter.base import QmtDataAdapter
from src.core.config import settings
from src.core.exceptions import AdapterError
from src.core.logging import setup_logging
from src.datasource.qmt.command_gateway import QmtCommandGateway
from src.ws.manager import ConnectionManager

setup_logging()

qmt_adapter: QmtDataAdapter | None = None
qmt_command_gateway = QmtCommandGateway()
ws_manager = ConnectionManager()


def _sync_app_state(target_app: FastAPI) -> None:
    target_app.state.qmt_adapter = qmt_adapter
    target_app.state.qmt_command_gateway = qmt_command_gateway
    target_app.state.ws_manager = ws_manager


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期管理器.

    启动时创建并初始化 QMT 适配器，关闭时执行清理.
    生产 live QMT 在 Windows spike 完成前保持禁用。

    Args:
        _app: FastAPI 应用实例

    Yields:
        None
    """
    global qmt_adapter
    try:
        qmt_adapter = create_qmt_adapter()
        await qmt_adapter.initialize()
    except AdapterError:
        qmt_adapter = None
    _sync_app_state(_app)
    yield
    if qmt_adapter:
        await qmt_adapter.shutdown()
    qmt_adapter = None
    _sync_app_state(_app)


app = FastAPI(
    title="Mist DataSource - QMT Adapter",
    description="QMT 数据源适配器 - full-QMT bridge / mock diagnostics",
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

app.include_router(market_router, prefix="/api/qmt/market", tags=["Market"])
app.include_router(stock_router, prefix="/api/qmt/stock", tags=["Stock"])
app.include_router(financial_router, prefix="/api/qmt/financial", tags=["Financial"])
app.include_router(sector_router, prefix="/api/qmt/sector", tags=["Sector"])
app.include_router(etf_router, prefix="/api/qmt/etf", tags=["ETF"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
app.include_router(bridge_router, prefix="/qmt/bridge", tags=["QMT Bridge"])
