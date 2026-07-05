"""Unit tests for TDX route dependency state lookup."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from starlette.requests import Request
from starlette.websockets import WebSocket

from src.datasource.tdx.runtime import TdxRuntime
from tdx.routes.dependencies import get_tdx_provider
from tdx.routes.legacy.dependencies import (
    get_tdx_legacy_adapter,
    get_tdx_legacy_bridge,
    get_tdx_legacy_subscription_client,
    get_ws_manager,
)


async def _receive() -> dict[str, Any]:
    return {"type": "websocket.connect"}


async def _send(message: dict[str, Any]) -> None:
    _ = message


def _request(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/bars/query",
            "headers": [],
            "app": app,
        }
    )


def _websocket(app: FastAPI) -> WebSocket:
    return WebSocket(
        {
            "type": "websocket",
            "path": "/ws/quote/test-client",
            "headers": [],
            "query_string": b"",
            "app": app,
        },
        _receive,
        _send,
    )


def test_tdx_route_dependencies_read_runtime_components_from_app_state() -> None:
    app = FastAPI()
    adapter = object()
    provider = object()
    bridge = object()
    collector = object()
    subscription_client = object()
    ws_manager = object()
    runtime = TdxRuntime(
        adapter=adapter,
        provider=provider,
        bridge=bridge,
        collector=collector,
        subscription_client=subscription_client,
        ws_manager=ws_manager,
    )
    runtime.sync_app_state(app)

    request = _request(app)
    websocket = _websocket(app)

    assert get_tdx_legacy_adapter(request) is adapter
    assert get_tdx_provider(request) is provider
    assert get_tdx_legacy_bridge(websocket) is bridge
    assert get_tdx_legacy_subscription_client(websocket) is subscription_client
    assert get_ws_manager(websocket) is ws_manager
