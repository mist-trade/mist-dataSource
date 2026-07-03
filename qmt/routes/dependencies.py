from typing import Any

from fastapi import HTTPException, Request, WebSocket


def get_qmt_adapter(request: Request) -> Any:
    return getattr(request.app.state, "qmt_adapter", None)


def require_qmt_adapter(request: Request) -> Any:
    adapter = get_qmt_adapter(request)
    if adapter is None:
        raise HTTPException(status_code=503, detail="Adapter not initialized")
    return adapter


def get_ws_manager(websocket: WebSocket) -> Any:
    return getattr(websocket.app.state, "ws_manager", None)
