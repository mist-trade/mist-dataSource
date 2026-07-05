from collections.abc import Awaitable
from typing import Any

from fastapi import HTTPException, Request, WebSocket

from src.core.config import settings
from src.datasource.tdx_legacy.bridge import TdxLegacyBridge


def get_tdx_legacy_adapter(request: Request) -> Any:
    return getattr(request.app.state, "tdx_legacy_adapter", None)


def require_tdx_legacy_adapter(request: Request) -> Any:
    adapter = get_tdx_legacy_adapter(request)
    if adapter is None:
        raise HTTPException(status_code=503, detail="Legacy TDX adapter not initialized")
    return adapter


async def call_tdx_legacy_adapter[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_ws_manager(websocket: WebSocket) -> Any:
    return getattr(websocket.app.state, "ws_manager", None)


def get_tdx_legacy_subscription_client(websocket: WebSocket) -> Any:
    return getattr(websocket.app.state, "tdx_legacy_subscription_client", None)


def get_tdx_legacy_bridge(websocket: WebSocket) -> TdxLegacyBridge:
    bridge = getattr(websocket.app.state, "tdx_legacy_bridge", None)
    if bridge is None:
        bridge = TdxLegacyBridge(
            queue_max_size=settings.tdx.ws_queue_max_size,
            max_subscriptions=settings.tdx.max_subscriptions,
        )
        websocket.app.state.tdx_legacy_bridge = bridge
    return bridge
