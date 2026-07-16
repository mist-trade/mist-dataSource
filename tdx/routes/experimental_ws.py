"""Experimental TDX realtime WebSocket endpoint.

Independent of the legacy ``/ws/quote`` route. Uses an isolated
``ConnectionManager`` instance so experimental frames never reach legacy
consumers and vice versa. The experimental Mist client connects here to receive
``tdx.experimental.snapshot`` frames plus ``ready``/``stream_started`` control
events.

Only mounted when ``TDX_REALTIME_MODE=builtin_experimental``.
"""

from __future__ import annotations

import json
from contextlib import suppress
from json import JSONDecodeError

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.datasource.tdx.experimental_gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_DRAFT_REVISION,
    ACCEPTED_PAYLOAD_TYPE,
    ACCEPTED_SCHEMA_VERSION,
)
from src.ws.protocol import ws_ready

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
                "datasourceBuildId": "mist-datasource-experimental",
                "bridgeBuildId": owner.bridge_build_id if owner else None,
            },
        ),
    )

    try:
        while True:
            raw = await websocket.receive_text()
            # The experimental endpoint is push-only from the server side.
            # Client messages are limited to ping for liveness.
            with suppress(JSONDecodeError):
                msg: object = json.loads(raw)
                if isinstance(msg, dict):
                    msg_dict: dict[str, object] = msg  # type: ignore[assignment]
                    if msg_dict.get("type") == "ping":
                        from src.ws.protocol import ws_pong

                        await manager.send_to_client(client_id, ws_pong("tdx"))
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(client_id)
