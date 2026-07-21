"""Experimental TDX realtime WebSocket endpoint.

Uses a dedicated ``ConnectionManager`` instance. The Mist client connects here to receive
``tdx.experimental.snapshot`` frames plus ``ready``/``stream_started`` control
events.

Mounted unconditionally by the TDX datasource.
"""

from __future__ import annotations

import json
from contextlib import suppress
from json import JSONDecodeError
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.datasource.tdx.experimental_gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_DRAFT_REVISION,
    ACCEPTED_PAYLOAD_TYPE,
    ACCEPTED_SCHEMA_VERSION,
)
from src.ws.protocol import ws_error, ws_ready, ws_subscription_ack

router = APIRouter()


def _get_experimental_ws_manager(websocket: WebSocket):
    manager = getattr(websocket.app.state, "tdx_experimental_ws_manager", None)
    if manager is None:
        raise RuntimeError("experimental ws manager not initialized on app.state")
    return manager


def _get_gateway(websocket: WebSocket):
    gateway = getattr(websocket.app.state, "tdx_experimental_gateway", None)
    if gateway is None:
        raise RuntimeError("experimental gateway not initialized on app.state")
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


@router.websocket("/ws/tdx-experimental/{client_id}")
async def experimental_tdx_realtime(websocket: WebSocket, client_id: str) -> None:
    """Experimental realtime WS: push snapshot frames + control events."""
    manager = _get_experimental_ws_manager(websocket)
    gateway = _get_gateway(websocket)

    accepted = await manager.connect_unique(websocket, client_id)
    if not accepted:
        await websocket.close(code=1008, reason="client_id already connected")
        return

    # Send ready with contract tuple + current epoch (late-connect recovery).
    owner = gateway.owner
    await manager.send_to_client(
        client_id,
        ws_ready(
            "tdx",
            {
                "mode": "builtin_experimental",
                "payloadType": ACCEPTED_PAYLOAD_TYPE,
                "schemaVersion": ACCEPTED_SCHEMA_VERSION,
                "draftRevision": ACCEPTED_DRAFT_REVISION,
                "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
                "currentStreamEpoch": owner.stream_epoch if owner else None,
                "currentGeneration": owner.generation if owner else None,
                "ownerId": owner.owner_id if owner else None,
                "datasourceBuildId": "mist-datasource-experimental",
                "bridgeBuildId": owner.bridge_build_id if owner else None,
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
                    if msg_dict.get("type") == "ping":
                        from src.ws.protocol import ws_pong

                        await manager.send_to_client(client_id, ws_pong("tdx"))
                    elif msg_dict.get("type") == "sync_subscriptions":
                        typed_symbols = _parse_symbols(msg_dict.get("symbols"))
                        if typed_symbols is None:
                            await manager.send_to_client(
                                client_id,
                                ws_error(
                                    provider="tdx",
                                    code="TDX_SUBSCRIPTIONS_INVALID",
                                    message="symbols must be a list of strings",
                                    retryable=False,
                                ),
                            )
                            continue
                        await gateway.sync_desired(typed_symbols)
                        await manager.send_to_client(
                            client_id,
                            ws_subscription_ack(
                                provider="tdx",
                                msg_type="subscribed",
                                accepted=typed_symbols,
                                rejected=[],
                                active=typed_symbols,
                            ),
                        )
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(client_id)
