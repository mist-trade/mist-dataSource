"""Instance 2 - QMT Adapter FastAPI application (Port 9002)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapter import create_qmt_adapter
from src.adapter.base import MarketDataAdapter
from src.core.config import settings
from src.core.logging import setup_logging
from src.ws.manager import ConnectionManager

# Setup logging
setup_logging()

# Global state
qmt_adapter: MarketDataAdapter | None = None
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    global qmt_adapter
    # Startup
    qmt_adapter = create_qmt_adapter(
        path=settings.qmt.path, account_id=settings.qmt.account_id
    )
    await qmt_adapter.initialize()
    yield
    # Shutdown
    if qmt_adapter:
        await qmt_adapter.shutdown()


app = FastAPI(
    title="Mist DataSource - QMT Adapter",
    description="miniQMT 数据源适配器 - 提供行情和交易接口",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "instance": "qmt",
        "adapter": type(qmt_adapter).__name__ if qmt_adapter else "none",
        "connections": ws_manager.connection_count,
    }


# Route registration
from qmt.routes.market import router as market_router
from qmt.routes.trade import router as trade_router
from qmt.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/qmt/market", tags=["Market"])
app.include_router(trade_router, prefix="/api/qmt/trade", tags=["Trade"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
