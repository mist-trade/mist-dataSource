"""TDX 适配器 FastAPI 应用入口 (Port 9001).

启动方式: uvicorn tdx.main:app --port 9001 --reload
对应 TDX SDK: tqcenter.tq (通过 MarketDataAdapter 适配器层调用)
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.adapter import create_tdx_adapter
from src.adapter.base import TdxDataAdapter
from src.core.config import settings
from src.core.logging import setup_logging
from src.datasource.tdx.runtime import TdxRuntime
from src.datasource.tdx_provider import TdxDatasourceProvider
from src.ws.manager import ConnectionManager
from tdx.routes.legacy.client import router as client_router
from tdx.routes.legacy.etf import router as etf_router
from tdx.routes.legacy.financial import router as financial_router
from tdx.routes.legacy.market import router as market_router
from tdx.routes.legacy.sector import router as sector_router
from tdx.routes.legacy.stock import router as stock_router
from tdx.routes.legacy.value import router as value_router
from tdx.routes.v1 import router as v1_router
from tdx.routes.ws import router as ws_router

setup_logging()

tdx_adapter: TdxDataAdapter | None = None
tdx_provider: TdxDatasourceProvider | None = None
tdx_bridge: Any | None = None
tdx_collector: Any | None = None
tdx_subscription_client: Any | None = None
ws_manager = ConnectionManager()
tdx_runtime: TdxRuntime | None = None
_tdx_provider_owned_by_main: TdxDatasourceProvider | None = None
_tdx_adapter_owned_by_main: TdxDataAdapter | None = None
_tdx_bridge_owned_by_main: Any | None = None
_tdx_collector_owned_by_main: Any | None = None
_tdx_subscription_client_owned_by_main: Any | None = None


def _sync_app_state(target_app: FastAPI) -> None:
    target_app.state.tdx_runtime = tdx_runtime
    target_app.state.tdx_adapter = tdx_adapter
    target_app.state.tdx_provider = tdx_provider
    target_app.state.tdx_bridge = tdx_bridge
    target_app.state.tdx_collector = tdx_collector
    target_app.state.tdx_subscription_client = tdx_subscription_client
    target_app.state.ws_manager = ws_manager


def _runtime_from_globals() -> TdxRuntime:
    return TdxRuntime(
        adapter=tdx_adapter,
        provider=tdx_provider,
        bridge=tdx_bridge,
        collector=tdx_collector,
        subscription_client=tdx_subscription_client,
        ws_manager=ws_manager,
        adapter_factory=create_tdx_adapter,
        provider_factory=TdxDatasourceProvider,
    )


def _sync_globals_from_runtime(runtime: TdxRuntime) -> None:
    global _tdx_adapter_owned_by_main, _tdx_bridge_owned_by_main
    global _tdx_collector_owned_by_main, _tdx_provider_owned_by_main
    global _tdx_subscription_client_owned_by_main
    global tdx_adapter, tdx_bridge, tdx_collector, tdx_provider, tdx_subscription_client

    tdx_adapter = runtime.adapter
    tdx_provider = runtime.provider
    tdx_bridge = runtime.bridge
    tdx_collector = runtime.collector
    tdx_subscription_client = runtime.subscription_client
    _tdx_adapter_owned_by_main = runtime.adapter if runtime.owns_adapter else None
    _tdx_provider_owned_by_main = runtime.provider if runtime.owns_provider else None
    _tdx_bridge_owned_by_main = runtime.bridge if runtime.owns_bridge else None
    _tdx_collector_owned_by_main = runtime.collector if runtime.owns_collector else None
    _tdx_subscription_client_owned_by_main = (
        runtime.subscription_client if runtime.owns_subscription_client else None
    )


def _clear_owned_globals_after_stop(
    *,
    owned_adapter: Any | None,
    owned_provider: Any | None,
    owned_bridge: Any | None,
    owned_collector: Any | None,
    owned_subscription_client: Any | None,
) -> None:
    global _tdx_adapter_owned_by_main, _tdx_bridge_owned_by_main
    global _tdx_collector_owned_by_main, _tdx_provider_owned_by_main
    global _tdx_subscription_client_owned_by_main
    global tdx_adapter, tdx_bridge, tdx_collector, tdx_provider, tdx_subscription_client

    if tdx_subscription_client is owned_subscription_client:
        tdx_subscription_client = None
    if tdx_collector is owned_collector:
        tdx_collector = None
    if tdx_bridge is owned_bridge:
        tdx_bridge = None
    if tdx_provider is owned_provider:
        tdx_provider = None
    if tdx_adapter is owned_adapter:
        tdx_adapter = None

    _tdx_subscription_client_owned_by_main = None
    _tdx_collector_owned_by_main = None
    _tdx_bridge_owned_by_main = None
    _tdx_provider_owned_by_main = None
    _tdx_adapter_owned_by_main = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期管理器.

    启动时创建并初始化 TDX 适配器，关闭时执行清理.
    对应 TDX SDK: tq.initialize(__file__)

    Args:
        app: FastAPI 应用实例

    Yields:
        None
    """
    global tdx_runtime
    runtime = _runtime_from_globals()
    tdx_runtime = runtime
    await runtime.start()
    _sync_globals_from_runtime(runtime)
    _sync_app_state(_app)

    try:
        yield
    finally:
        owned_subscription_client = _tdx_subscription_client_owned_by_main
        owned_collector = _tdx_collector_owned_by_main
        owned_bridge = _tdx_bridge_owned_by_main
        owned_provider = _tdx_provider_owned_by_main
        owned_adapter = _tdx_adapter_owned_by_main
        try:
            await runtime.stop()
        finally:
            _clear_owned_globals_after_stop(
                owned_adapter=owned_adapter,
                owned_provider=owned_provider,
                owned_bridge=owned_bridge,
                owned_collector=owned_collector,
                owned_subscription_client=owned_subscription_client,
            )
            if tdx_runtime is runtime:
                tdx_runtime = None
            _sync_app_state(_app)


app = FastAPI(
    title="Mist DataSource - TDX Adapter",
    description="通达信数据源适配器 - 提供 HTTP/WebSocket 接口",
    version="0.1.0",
    lifespan=lifespan,
)
_sync_app_state(app)

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
    return await _runtime_from_globals().health(instance="tdx")


app.include_router(v1_router, tags=["V1"])
app.include_router(market_router, prefix="/api/tdx", tags=["Market"])
app.include_router(stock_router, prefix="/api/tdx", tags=["Stock"])
app.include_router(financial_router, prefix="/api/tdx", tags=["Financial"])
app.include_router(value_router, prefix="/api/tdx", tags=["Value"])
app.include_router(sector_router, prefix="/api/tdx", tags=["Sector"])
app.include_router(etf_router, prefix="/api/tdx", tags=["ETF"])
app.include_router(client_router, prefix="/api/tdx", tags=["Client"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
