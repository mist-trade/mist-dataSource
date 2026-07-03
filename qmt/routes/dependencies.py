from collections.abc import Awaitable
from typing import Any

from fastapi import HTTPException, Request, WebSocket

from src.ws.manager import ConnectionManager


def get_qmt_adapter(request: Request | WebSocket) -> Any:
    return getattr(request.app.state, "qmt_adapter", None)


def require_qmt_adapter(request: Request) -> Any:
    adapter = get_qmt_adapter(request)
    if adapter is None:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    return adapter


async def call_qmt_adapter[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def get_ws_manager(websocket: WebSocket) -> Any:
    manager = getattr(websocket.app.state, "ws_manager", None)
    if manager is None:
        manager = ConnectionManager()
        websocket.app.state.ws_manager = manager
    return manager
