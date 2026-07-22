"""TDX datasource application (port 9001).

Historical and reference requests use the official TDX HTTP endpoint on
port 17709. Realtime defaults to ``builtin`` and is omitted only when an
operator explicitly selects ``off`` for rollback.
"""

from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from typing import Any, Literal, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.logging import setup_logging
from src.datasource.tdx.provider import TdxDatasourceProvider
from src.datasource.tdx.realtime.runtime import TdxRealtimeGateway
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_stream_started
from tdx.routes.bridge import router as bridge_router
from tdx.routes.realtime import router as realtime_router
from tdx.routes.v1 import router as v1_router

setup_logging()

TdxRealtimeMode = Literal["off", "builtin"]
TDX_REALTIME_MODES = {"off", "builtin"}


def _validated_realtime_mode(value: str) -> TdxRealtimeMode:
    if value not in TDX_REALTIME_MODES:
        raise ValueError("TDX_REALTIME_MODE must be one of: off, builtin")
    return cast(TdxRealtimeMode, value)


def create_tdx_app(
    *,
    realtime_mode: str | None = None,
    provider: TdxDatasourceProvider | None = None,
    gateway: TdxRealtimeGateway | None = None,
    manager: ConnectionManager | None = None,
) -> FastAPI:
    """Build an isolated TDX app whose dependencies are owned by ``app.state``."""
    mode = _validated_realtime_mode(realtime_mode or settings.tdx.realtime_mode)
    app_provider = provider or TdxDatasourceProvider()
    owns_provider = provider is None
    app_manager = manager
    app_gateway = gateway

    if mode == "builtin":
        app_manager = app_manager or ConnectionManager()

        async def broadcast_epoch_change(
            stream_epoch: str,
            generation: int,
            owner_id: str,
            bridge_build_id: str,
        ) -> None:
            assert app_manager is not None
            await app_manager.broadcast(
                ws_stream_started(
                    "tdx",
                    {
                        "payloadType": "mist.realtime.native_snapshot",
                        "schemaVersion": 1,
                        "source": "tdx",
                        "sequenceScope": "symbol",
                        "acquisitionProfile": "tdx.get_market_snapshot",
                        "streamEpoch": stream_epoch,
                        "generation": generation,
                        "sequence": 0,
                        "mode": "builtin",
                        "ownerId": owner_id,
                        "bridgeBuildId": bridge_build_id,
                    },
                )
            )

        app_gateway = app_gateway or TdxRealtimeGateway(
            max_subscriptions=settings.tdx.max_subscriptions,
            on_epoch_change=broadcast_epoch_change,
        )

    @asynccontextmanager
    async def lifespan(_target: FastAPI) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            if owns_provider:
                await app_provider.aclose()

    target = FastAPI(
        title="Mist DataSource - TDX",
        description="TDX HTTP provider and builtin realtime bridge",
        version="1.0.0",
        lifespan=lifespan,
    )
    target.state.tdx_realtime_mode = mode
    target.state.tdx_provider = app_provider
    target.state.tdx_realtime_gateway = app_gateway
    target.state.tdx_realtime_ws_manager = app_manager

    target.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @target.get("/health")
    async def health() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        current_provider = target.state.tdx_provider
        try:
            value: Any = await current_provider.health()
            if not isinstance(value, Mapping):
                provider_health = {
                    "tdxHttpReachable": False,
                    "lastError": "TDX provider health returned a non-mapping payload",
                }
            else:
                payload = cast(Mapping[str, Any], value)
                provider_health = {
                    "tdxHttpReachable": bool(payload.get("tdxHttpReachable", False)),
                    "lastError": payload.get("lastError"),
                }
        except Exception as exc:
            provider_health = {"tdxHttpReachable": False, "lastError": str(exc)}

        current_gateway: TdxRealtimeGateway | None = target.state.tdx_realtime_gateway
        current_manager: ConnectionManager | None = target.state.tdx_realtime_ws_manager
        bridge_health = (
            await current_gateway.health()
            if current_gateway is not None
            else {"tdxRealtimeBridgeReady": False}
        )
        connections = current_manager.connection_count if current_manager else 0
        return {
            "status": "ok",
            "instance": "tdx",
            "connections": connections,
            "wsConnected": connections > 0,
            **provider_health,
            **bridge_health,
        }

    target.include_router(v1_router, tags=["V1"])
    if mode == "builtin":
        target.include_router(bridge_router, tags=["TDX Bridge"])
        target.include_router(realtime_router, tags=["TDX Realtime"])
    return target


app = create_tdx_app()
