"""Instance 1 - TDX Adapter FastAPI application (Port 9001)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapter import create_tdx_adapter
from src.core.config import settings
from src.adapter.base import MarketDataAdapter
from src.core.logging import setup_logging
from src.ws.manager import ConnectionManager

# Setup logging
setup_logging()

# Global state
tdx_adapter: MarketDataAdapter | None = None
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager.

    Handles startup and shutdown events.
    """
    global tdx_adapter
    # Startup
    tdx_adapter = create_tdx_adapter()
    await tdx_adapter.initialize()
    yield
    # Shutdown
    if tdx_adapter:
        await tdx_adapter.shutdown()


app = FastAPI(
    title="Mist DataSource - TDX Adapter",
    description="通达信数据源适配器 - 提供 HTTP/WebSocket 接口",
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
        "instance": "tdx",
        "adapter": type(tdx_adapter).__name__ if tdx_adapter else "none",
        "connections": ws_manager.connection_count,
    }


# Route registration
from instance1.routes.market import router as market_router
from instance1.routes.ws import router as ws_router

app.include_router(market_router, prefix="/api/tdx", tags=["Market"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
