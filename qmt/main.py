"""QMT datasource FastAPI application entrypoint (Port 9002).

The product QMT HTTP bridge and historical APIs are always available. The
memory-only realtime transport is mounted only when explicitly enabled.
"""

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qmt.routes.bridge import router as bridge_router
from qmt.routes.realtime import router as realtime_router
from qmt.routes.v1 import router as v1_router
from qmt.routes.ws import router as ws_router
from src.core.config import settings
from src.core.logging import setup_logging
from src.datasource.qmt.command_gateway import QmtCommandGateway
from src.datasource.qmt.realtime import QmtRealtimeCollector
from src.datasource.qmt_provider import QmtDatasourceProvider
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_error, ws_realtime_snapshot, ws_stream_started

setup_logging()

QmtRealtimeMode = Literal["off", "builtin"]
QMT_REALTIME_MODES = {"off", "builtin"}


def _validated_realtime_mode(value: str) -> QmtRealtimeMode:
    if value not in QMT_REALTIME_MODES:
        raise ValueError("QMT_REALTIME_MODE must be one of: off, builtin")
    return cast(QmtRealtimeMode, value)


def create_qmt_app(
    *,
    realtime_mode: str | None = None,
    gateway: QmtCommandGateway | None = None,
    provider: QmtDatasourceProvider | None = None,
    collector_now: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Build an isolated QMT app for the selected realtime mode."""
    mode = _validated_realtime_mode(realtime_mode or settings.qmt.realtime_mode)
    app_gateway = gateway or QmtCommandGateway()
    app_provider = provider or QmtDatasourceProvider()
    manager: ConnectionManager | None = None
    collector: QmtRealtimeCollector | None = None

    if mode == "builtin":
        manager = ConnectionManager()

        async def publish_snapshot(data: dict[str, Any]) -> None:
            assert manager is not None
            await manager.broadcast(ws_realtime_snapshot("qmt", data))

        async def publish_error(code: str, message: str) -> None:
            assert manager is not None
            await manager.broadcast(
                ws_error(
                    provider="qmt",
                    code=code,
                    message=message,
                    retryable=True,
                    details={},
                )
            )

        async def publish_epoch(data: dict[str, Any]) -> None:
            assert manager is not None
            await manager.broadcast(ws_stream_started("qmt", data))

        collector = QmtRealtimeCollector(
            gateway=app_gateway,
            publisher=publish_snapshot,
            epoch_publisher=publish_epoch,
            error_publisher=publish_error,
            now=collector_now,
        )

    @asynccontextmanager
    async def lifespan(target_app: FastAPI) -> AsyncGenerator[None]:
        active_collector: QmtRealtimeCollector | None = getattr(
            target_app.state, "qmt_realtime_collector", None
        )
        if active_collector is not None:
            await active_collector.start()
        try:
            yield
        finally:
            if active_collector is not None:
                await active_collector.stop()

    target = FastAPI(
        title="Mist DataSource - QMT",
        description="QMT datasource - native bars and full-QMT HTTP polling bridge",
        version="0.1.0",
        lifespan=lifespan,
    )
    target.state.qmt_realtime_mode = mode
    target.state.qmt_command_gateway = app_gateway
    target.state.qmt_provider = app_provider
    if manager is not None and collector is not None:
        target.state.qmt_realtime_ws_manager = manager
        target.state.qmt_realtime_collector = collector

    target.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @target.get("/health")
    async def health() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        current_gateway: QmtCommandGateway = target.state.qmt_command_gateway
        return {
            "status": "ok",
            "instance": "qmt",
            "bridge": current_gateway.health(),
        }

    target.include_router(v1_router, tags=["V1"])
    target.include_router(bridge_router, prefix="/qmt/bridge", tags=["QMT Bridge"])
    if mode == "builtin":
        target.include_router(ws_router, tags=["QMT Realtime WebSocket"])
        target.include_router(realtime_router, tags=["QMT Realtime"])
    return target


qmt_command_gateway = QmtCommandGateway()
qmt_provider: QmtDatasourceProvider | None = QmtDatasourceProvider()
app = create_qmt_app(gateway=qmt_command_gateway, provider=qmt_provider)
