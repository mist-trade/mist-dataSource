"""TDX datasource application (port 9001).

Historical and reference requests use the official TDX HTTP endpoint on
port 17709. Realtime snapshots are owned by the terminal builtin bridge.
"""

from collections.abc import Mapping
from contextlib import asynccontextmanager
from typing import Any, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logging import setup_logging
from src.datasource.tdx.experimental_gateway import ExperimentalTdxRealtimeGateway
from src.datasource.tdx_provider import TdxDatasourceProvider
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_stream_started
from tdx.routes.experimental import router as bridge_router
from tdx.routes.experimental_ws import router as realtime_ws_router
from tdx.routes.v1 import router as v1_router

setup_logging()

tdx_provider: TdxDatasourceProvider | None = None
tdx_experimental_gateway: ExperimentalTdxRealtimeGateway | None = None
tdx_experimental_ws_manager: ConnectionManager | None = None
_tdx_provider_owned_by_main: TdxDatasourceProvider | None = None


async def _broadcast_epoch_change(
    stream_epoch: str,
    generation: int,
    owner_id: str,
    bridge_build_id: str,
) -> None:
    if tdx_experimental_ws_manager is None:
        return
    await tdx_experimental_ws_manager.broadcast(
        ws_stream_started(
            "tdx",
            {
                "streamEpoch": stream_epoch,
                "generation": generation,
                "mode": "builtin_experimental",
                "ownerId": owner_id,
                "bridgeBuildId": bridge_build_id,
            },
        )
    )


def _sync_app_state(target: FastAPI) -> None:
    target.state.tdx_provider = tdx_provider
    target.state.tdx_experimental_gateway = tdx_experimental_gateway
    target.state.tdx_experimental_ws_manager = tdx_experimental_ws_manager


@asynccontextmanager
async def lifespan(target: FastAPI):
    global _tdx_provider_owned_by_main
    global tdx_experimental_gateway, tdx_experimental_ws_manager, tdx_provider

    owned_provider: TdxDatasourceProvider | None = None
    if tdx_provider is None:
        tdx_provider = TdxDatasourceProvider()
        owned_provider = tdx_provider
        _tdx_provider_owned_by_main = owned_provider
    if tdx_experimental_ws_manager is None:
        tdx_experimental_ws_manager = ConnectionManager()
    if tdx_experimental_gateway is None:
        tdx_experimental_gateway = ExperimentalTdxRealtimeGateway(
            max_subscriptions=settings.tdx.max_subscriptions,
            on_epoch_change=_broadcast_epoch_change,
        )
    _sync_app_state(target)

    try:
        yield
    finally:
        try:
            if owned_provider is not None:
                await owned_provider.aclose()
        finally:
            if tdx_provider is owned_provider:
                tdx_provider = None
            _tdx_provider_owned_by_main = None
            _sync_app_state(target)


app = FastAPI(
    title="Mist DataSource - TDX",
    description="TDX HTTP provider and builtin realtime bridge",
    version="1.0.0",
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


async def _provider_health() -> dict[str, Any]:
    if tdx_provider is None:
        return {"tdxHttpReachable": False, "lastError": "TDX provider is not initialized"}
    try:
        value: Any = await tdx_provider.health()
        if not isinstance(value, Mapping):
            return {
                "tdxHttpReachable": False,
                "lastError": "TDX provider health returned a non-mapping payload",
            }
        payload = cast(Mapping[str, Any], value)
        return {
            "tdxHttpReachable": bool(payload.get("tdxHttpReachable", False)),
            "lastError": payload.get("lastError"),
        }
    except Exception as exc:
        return {"tdxHttpReachable": False, "lastError": str(exc)}


@app.get("/health")
async def health() -> dict[str, Any]:
    provider_health = await _provider_health()
    bridge_health = (
        await tdx_experimental_gateway.health()
        if tdx_experimental_gateway is not None
        else {"tdxExperimentalBridgeReady": False}
    )
    connections = (
        tdx_experimental_ws_manager.connection_count
        if tdx_experimental_ws_manager is not None
        else 0
    )
    return {
        "status": "ok",
        "instance": "tdx",
        "connections": connections,
        "wsConnected": connections > 0,
        **provider_health,
        **bridge_health,
    }


app.include_router(v1_router, tags=["V1"])
app.include_router(bridge_router, tags=["TDX Bridge"])
app.include_router(realtime_ws_router, tags=["TDX Realtime"])
