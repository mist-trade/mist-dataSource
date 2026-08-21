"""QMT datasource FastAPI application entrypoint (Port 9002).

The product QMT HTTP bridge and historical APIs are always available. The
memory-only realtime transport defaults to ``builtin`` and is mounted unless
an operator explicitly selects ``off`` for rollback.
"""

import asyncio
import contextlib
import os
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Literal, cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace

from qmt.routes.bridge import router as bridge_router
from qmt.routes.realtime import router as realtime_router
from qmt.routes.v1 import router as v1_router
from src.core.config import settings
from src.core.logging import get_logger, setup_logging
from src.core.otel import force_flush, init_otel, instrument_app
from src.datasource import metrics as ds_metrics
from src.datasource.qmt.provider import QmtDatasourceProvider
from src.datasource.qmt.realtime.gateway import QmtCommandGateway
from src.datasource.qmt.realtime.runtime import QmtRealtimeCollector
from src.datasource.qmt.realtime.subscription import (
    QMT_CONTEXT_REBUILD_OBSERVATION_PATH_ENV,
    QmtSubscriptionController,
    QmtSubscriptionJournal,
    configured_qmt_unsubscribe_success_values,
)
from src.ws.health_contract import QmtDatasourceHealth
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_error, ws_realtime_snapshot

setup_logging()
init_otel("qmt-datasource")
ds_metrics.init_metrics()

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
    subscription_journal: QmtSubscriptionJournal | None = None,
    unsubscribe_success_values: frozenset[int] | None = None,
) -> FastAPI:
    """Build an isolated QMT app for the selected realtime mode."""
    mode = _validated_realtime_mode(realtime_mode or settings.qmt.realtime_mode)
    app_gateway = gateway or QmtCommandGateway()
    app_provider = provider or QmtDatasourceProvider()
    manager: ConnectionManager | None = None
    collector: QmtRealtimeCollector | None = None
    subscription_controller: QmtSubscriptionController | None = None

    if mode == "builtin":
        manager = ConnectionManager()

        async def publish_snapshot(data: dict[str, Any]) -> None:
            assert manager is not None
            if collector is not None:
                collector.record_snapshot(str(data.get("capturedAt", "")))
            _log.info("broadcast source=qmt clients=%d", manager.connection_count)
            ds_metrics.set_ws_clients("qmt", manager.connection_count)
            await manager.broadcast(ws_realtime_snapshot("qmt", data))

        async def publish_error(code: str, message: str) -> None:
            assert manager is not None
            if collector is not None:
                collector.record_error(code, message)
            await manager.broadcast(
                ws_error(
                    provider="qmt",
                    code=code,
                    message=message,
                    retryable=True,
                    details={},
                )
            )

        collector = QmtRealtimeCollector(
            gateway=app_gateway,
            publisher=publish_snapshot,
            error_publisher=publish_error,
            now=collector_now,
        )
        journal = subscription_journal or QmtSubscriptionJournal()
        subscription_controller = QmtSubscriptionController(
            journal=journal,
            owner_validator=app_gateway.validate_owner,
            publisher=publish_snapshot,
            unsubscribe_success_values=(
                unsubscribe_success_values
                if unsubscribe_success_values is not None
                else configured_qmt_unsubscribe_success_values()
            ),
        )
        observation_path = os.environ.get(
            QMT_CONTEXT_REBUILD_OBSERVATION_PATH_ENV,
            str(journal.path.with_name("context-rebuild-observation.json")),
        )
        subscription_controller.consume_rebuilt_context_observation(observation_path)

    @asynccontextmanager
    async def lifespan(target_app: FastAPI) -> AsyncGenerator[None]:
        active_collector: QmtRealtimeCollector | None = getattr(
            target_app.state, "qmt_realtime_collector", None
        )
        if active_collector is not None:
            await active_collector.start()
        tcp_server: asyncio.AbstractServer | None = None
        stall_watchdog: asyncio.Task[None] | None = None
        subscription_controller = getattr(
            target_app.state, "qmt_subscription_controller", None
        )
        if mode == "builtin" and subscription_controller is not None:
            # Symmetry with TDX: observe snapshot-age gauge for QMT too.
            if active_collector is not None:
                ds_metrics.register_snapshot_age_callback(
                    "qmt",
                    lambda: active_collector.health()["lastSnapshotAgeSeconds"],
                )
            # E: persistent TCP ingestion for bridge frames (change E).
            from src.datasource.realtime_tcp import serve as serve_realtime_tcp

            async def ingest_qmt(frame: dict[str, Any]) -> None:
                await subscription_controller.accept_snapshot(
                    frame["ownerId"],
                    frame["leaseToken"],
                    frame["generation"],
                    frame["subscriptionId"],
                    frame["capturedAt"],
                    frame["native"],
                )

            tcp_server = await serve_realtime_tcp(
                host=settings.qmt.realtime_tcp_host,
                port=settings.qmt.realtime_tcp_port,
                provider="qmt",
                ingest=ingest_qmt,
            )
            stall_watchdog = asyncio.create_task(
                subscription_controller.run_recovery_watchdog()
            )
        try:
            yield
        finally:
            if stall_watchdog is not None:
                stall_watchdog.cancel()
                with contextlib.suppress(BaseException):
                    await stall_watchdog
            if tcp_server is not None:
                tcp_server.close()
                await tcp_server.wait_closed()
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
    if subscription_controller is not None:
        target.state.qmt_subscription_controller = subscription_controller

    target.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @target.get("/health", response_model=QmtDatasourceHealth)
    async def health() -> dict[str, Any]:  # pyright: ignore[reportUnusedFunction]
        current_gateway: QmtCommandGateway = target.state.qmt_command_gateway
        return {
            "status": "ok",
            "instance": "qmt",
            "realtimeMode": mode,
            "bridge": current_gateway.health(),
            "realtime": (
                target.state.qmt_realtime_collector.health()
                if hasattr(target.state, "qmt_realtime_collector")
                else {"state": "off"}
            ),
            "subscriptions": (
                target.state.qmt_subscription_controller.health()
                if hasattr(target.state, "qmt_subscription_controller")
                else {"ready": False}
            ),
        }

    target.include_router(v1_router, tags=["V1"])
    target.include_router(bridge_router, prefix="/qmt/bridge", tags=["QMT Bridge"])
    if mode == "builtin":
        target.include_router(realtime_router, tags=["QMT Realtime"])
    return target


_log = get_logger(__name__)
_tracer = trace.get_tracer("mist-datasource")


def _build_app_with_startup_trace() -> FastAPI:
    """Wrap app creation in a qmt.startup span so startup failures (e.g. the
    ambiguous context-rebuild observation state) are directly observable:
    error log (stdout) -> errored span -> synchronous force_flush -> re-raise.
    """
    with _tracer.start_as_current_span("qmt.startup") as span:
        try:
            app = create_qmt_app()
        except Exception as exc:
            span.set_status(trace.StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            _log.error("qmt startup failed: %s", exc)
            force_flush()  # sync export before the process exits
            raise
        span.set_status(trace.StatusCode.OK)
        ds_metrics.set_startup_ok("qmt", True)
        return app


app = _build_app_with_startup_trace()
instrument_app(app)
