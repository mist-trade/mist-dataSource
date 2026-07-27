"""QMT realtime WebSocket and loopback-only diagnostics."""

import json
from contextlib import suppress
from json import JSONDecodeError
from typing import Any, cast

from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from src.core.local_bridge import is_trusted_local_bridge_peer
from src.datasource.qmt.realtime.runtime import QmtRealtimeCollector
from src.datasource.qmt.realtime.subscription import QmtSubscriptionController
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_error, ws_pong, ws_ready, ws_subscription_result

router = APIRouter()


def _require_loopback(request: Request) -> None:
    client = request.client
    if client is None or not is_trusted_local_bridge_peer(client.host):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "QMT_REALTIME_NOT_LOOPBACK",
                "message": "QMT realtime diagnostics are loopback-only",
                "retryable": False,
            },
        )


@router.get("/qmt/realtime/health")
async def realtime_health(request: Request) -> dict[str, Any]:
    _require_loopback(request)
    if request.query_params:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "QMT_REALTIME_UNKNOWN_FIELDS",
                "message": "QMT realtime health accepts no query fields",
                "retryable": False,
                "fields": sorted(request.query_params.keys()),
            },
        )
    collector: QmtRealtimeCollector | None = getattr(
        request.app.state, "qmt_realtime_collector", None
    )
    if collector is None:
        raise HTTPException(status_code=404, detail="QMT realtime is disabled")
    return collector.health()


def _collector(websocket: WebSocket) -> QmtRealtimeCollector:
    return websocket.app.state.qmt_realtime_collector


def _manager(websocket: WebSocket) -> ConnectionManager:
    return websocket.app.state.qmt_realtime_ws_manager


def _subscription_controller(websocket: WebSocket) -> QmtSubscriptionController:
    return websocket.app.state.qmt_subscription_controller


def _is_leader(collector: QmtRealtimeCollector, client_id: str) -> bool:
    return collector.leader_client_id == client_id or collector.claim_leader(client_id)


def _symbols(message: dict[str, Any]) -> list[str] | None:
    value = message.get("symbols", [])
    if not isinstance(value, list):
        return None
    items = cast(list[Any], value)
    if not all(isinstance(item, str) for item in items):
        return None
    return cast(list[str], items)


@router.websocket("/ws/realtime/qmt/{client_id}")
async def websocket_quote(websocket: WebSocket, client_id: str) -> None:
    manager = _manager(websocket)
    collector = _collector(websocket)
    subscription_controller = _subscription_controller(websocket)
    if not await manager.connect_unique(websocket, client_id):
        await websocket.accept()
        await websocket.send_text(
            ws_error(
                provider="qmt",
                code="DATASOURCE_WS_DUPLICATE_CLIENT",
                message="A WebSocket client with this client_id is already connected",
                retryable=False,
                details={"clientId": client_id},
            ).to_json()
        )
        await websocket.close()
        return

    collector.claim_leader(client_id)
    ready_data = collector.ready_contract()
    bridge = collector.gateway.health()
    ready_data.update(
        {
            "leaderClientId": collector.leader_client_id,
            "active": subscription_controller.registry.public_value(),
            "collectorReady": bridge["ready"],
            "generation": bridge["ownerGeneration"],
            "ownerId": bridge["ownerId"],
        }
    )
    await websocket.send_text(ws_ready("qmt", ready_data).to_json())

    try:
        while True:
            try:
                message = json.loads(await websocket.receive_text())
            except JSONDecodeError as exc:
                await websocket.send_text(
                    ws_error(
                        provider="qmt",
                        code="DATASOURCE_WS_INVALID_MESSAGE",
                        message="WebSocket message must be valid JSON",
                        retryable=False,
                        details={"error": str(exc)},
                    ).to_json()
                )
                continue

            msg_type = message.get("type")
            if msg_type == "ping":
                if set(message) != {"type"}:
                    await _send_invalid_fields(websocket, message, {"type"})
                    continue
                await websocket.send_text(ws_pong("qmt").to_json())
                continue
            if msg_type not in {
                "sync_subscriptions",
                "subscribe",
                "unsubscribe",
                "get_subscriptions",
            }:
                continue
            allowed = (
                {"type", "symbols"}
                if msg_type == "sync_subscriptions"
                else {"type", "symbol"}
                if msg_type in {"subscribe", "unsubscribe"}
                else {"type"}
            )
            if set(message) != allowed:
                await _send_invalid_fields(websocket, message, allowed)
                continue
            if not _is_leader(collector, client_id):
                await websocket.send_text(
                    ws_error(
                        provider="qmt",
                        code="DATASOURCE_WS_NOT_LEADER",
                        message="Only the command leader can change QMT subscriptions",
                        retryable=False,
                        details={"leaderClientId": collector.leader_client_id},
                    ).to_json()
                )
                continue
            if msg_type == "sync_subscriptions":
                symbols = _symbols(message)
                if symbols is None:
                    await websocket.send_text(
                        ws_error(
                            provider="qmt",
                            code="DATASOURCE_WS_INVALID_SYMBOLS",
                            message="WebSocket symbols must be a list of strings",
                            retryable=False,
                            details={"operation": msg_type},
                        ).to_json()
                    )
                    continue
                response_type, data = await subscription_controller.execute(
                    msg_type, symbols=symbols
                )
            else:
                symbol = message.get("symbol")
                if msg_type != "get_subscriptions" and not isinstance(symbol, str):
                    await websocket.send_text(
                        ws_error(
                            provider="qmt",
                            code="DATASOURCE_WS_INVALID_SYMBOL",
                            message="WebSocket symbol must be a string",
                            retryable=False,
                            details={"operation": msg_type},
                        ).to_json()
                    )
                    continue
                response_type, data = await subscription_controller.execute(
                    msg_type,
                    symbol=cast(str | None, symbol),
                )
            await websocket.send_text(
                ws_subscription_result(
                    provider="qmt",
                    msg_type=response_type,
                    data=data,
                ).to_json()
            )
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        with suppress(Exception):
            await websocket.send_text(
                ws_error(
                    provider="qmt",
                    code="QMT_WS_INTERNAL_ERROR",
                    message=str(exc),
                    retryable=True,
                ).to_json()
            )
    finally:
        collector.disconnect(client_id)
        await manager.disconnect(client_id)


async def _send_invalid_fields(
    websocket: WebSocket, message: dict[str, Any], allowed: set[str]
) -> None:
    await websocket.send_text(
        ws_error(
            provider="qmt",
            code="DATASOURCE_WS_UNKNOWN_FIELDS",
            message="WebSocket message contains unknown fields",
            retryable=False,
            details={"fields": sorted(set(message) - allowed)},
        ).to_json()
    )
