"""TDX realtime WebSocket endpoint.

Uses a dedicated ``ConnectionManager`` instance. The Mist client connects here to receive
``realtime.native_snapshot`` frames plus formal ready/stream-started control
events.

Mounted only when ``TDX_REALTIME_MODE=builtin``.
"""

from __future__ import annotations

import json
from contextlib import suppress
from json import JSONDecodeError
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.datasource.tdx.realtime.gateway import ACCEPTED_SCHEMA_VERSION
from src.ws.protocol import ws_error, ws_pong, ws_ready, ws_subscription_result

router = APIRouter()


def _get_realtime_ws_manager(websocket: WebSocket):
    manager = getattr(websocket.app.state, "tdx_realtime_ws_manager", None)
    if manager is None:
        raise RuntimeError("realtime ws manager not initialized on app.state")
    return manager


def _get_gateway(websocket: WebSocket):
    gateway = getattr(websocket.app.state, "tdx_realtime_gateway", None)
    if gateway is None:
        raise RuntimeError("realtime gateway not initialized on app.state")
    return gateway


def _parse_symbols(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    symbols: list[str] = []
    for item in cast(list[object], value):
        if not isinstance(item, str):
            return None
        symbols.append(item)
    return symbols


@router.websocket("/ws/realtime/tdx/{client_id}")
async def tdx_realtime(websocket: WebSocket, client_id: str) -> None:
    """Formal realtime WS: push native snapshot frames and control events."""
    manager = _get_realtime_ws_manager(websocket)
    gateway = _get_gateway(websocket)

    accepted = await manager.connect_unique(websocket, client_id)
    if not accepted:
        await websocket.close(code=1008, reason="client_id already connected")
        return

    await manager.send_to_client(
        client_id,
        ws_ready(
            "tdx",
            {
                "mode": "builtin",
                "schemaVersion": ACCEPTED_SCHEMA_VERSION,
                "source": "TDX",
                "quality": "latest-state",
            },
        ),
    )

    try:
        while True:
            raw = await websocket.receive_text()
            # Control messages share this connection so the backend never needs
            # access to the loopback-only bridge HTTP routes.
            with suppress(JSONDecodeError):
                msg: object = json.loads(raw)
                if isinstance(msg, dict):
                    msg_dict: dict[str, object] = msg  # type: ignore[assignment]
                    msg_type = msg_dict.get("type")
                    if msg_type == "ping":
                        if set(msg_dict) != {"type"}:
                            await _send_invalid_fields(websocket, msg_dict, {"type"})
                            continue
                        await manager.send_to_client(client_id, ws_pong("tdx"))
                    elif msg_type in {
                        "sync_subscriptions",
                        "subscribe",
                        "unsubscribe",
                        "get_subscriptions",
                    }:
                        allowed = (
                            {"type", "symbols"}
                            if msg_type == "sync_subscriptions"
                            else {"type", "symbol"}
                            if msg_type in {"subscribe", "unsubscribe"}
                            else {"type"}
                        )
                        if set(msg_dict) != allowed:
                            await _send_invalid_fields(websocket, msg_dict, allowed)
                            continue
                        if msg_type == "sync_subscriptions":
                            typed_symbols = _parse_symbols(msg_dict.get("symbols"))
                            if typed_symbols is None:
                                await _send_control_error(
                                    manager,
                                    client_id,
                                    "TDX_SUBSCRIPTIONS_INVALID",
                                    "symbols must be a list of strings",
                                )
                                continue
                            response_type, data = await gateway.execute_control(
                                msg_type,
                                symbols=typed_symbols,
                            )
                        else:
                            symbol = msg_dict.get("symbol")
                            if msg_type != "get_subscriptions" and not isinstance(symbol, str):
                                await _send_control_error(
                                    manager,
                                    client_id,
                                    "TDX_SUBSCRIPTION_SYMBOL_INVALID",
                                    "symbol must be a string",
                                )
                                continue
                            response_type, data = await gateway.execute_control(
                                cast(str, msg_type),
                                symbol=cast(str | None, symbol),
                            )
                        await manager.send_to_client(
                            client_id,
                            ws_subscription_result(
                                provider="tdx",
                                msg_type=response_type,
                                data=data,
                            ),
                        )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(client_id)


async def _send_invalid_fields(
    websocket: WebSocket,
    message: dict[str, Any],
    allowed: set[str],
) -> None:
    await websocket.send_text(
        ws_error(
            provider="tdx",
            code="DATASOURCE_WS_UNKNOWN_FIELDS",
            message="WebSocket message contains unknown fields",
            retryable=False,
            details={"fields": sorted(set(message) - allowed)},
        ).to_json()
    )


async def _send_control_error(
    manager: Any,
    client_id: str,
    code: str,
    message: str,
) -> None:
    await manager.send_to_client(
        client_id,
        ws_error(
            provider="tdx",
            code=code,
            message=message,
            retryable=False,
        ),
    )
