"""Full-QMT command bridge routes."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from src.datasource.qmt.command_gateway import (
    QmtBridgeOwnershipError,
    QmtCommandGateway,
)

router = APIRouter()


class BridgeModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class OwnerRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    started_at: str | None = Field(default=None, alias="startedAt")
    last_poll_at: str | None = Field(default=None, alias="lastPollAt")


class PollRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    limit: int = 1


class ResultRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    command_id: str = Field(alias="commandId")
    ok: bool
    result: Any | None = None
    error: dict[str, Any] | None = None


def _get_gateway_from_state(state: Any) -> QmtCommandGateway:
    gateway = getattr(state, "qmt_command_gateway", None)
    if gateway is None:
        gateway = QmtCommandGateway()
        state.qmt_command_gateway = gateway
    return gateway


def get_gateway(request: Request) -> QmtCommandGateway:
    return _get_gateway_from_state(request.app.state)


@router.post("/owner")
async def register_owner(payload: OwnerRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    try:
        owner = gateway.register_owner(payload.owner_id)
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ownerId": owner.owner_id,
        "registeredAt": owner.registered_at,
        "lastHeartbeatAt": owner.last_heartbeat_at,
    }


@router.post("/poll")
async def poll_commands(payload: PollRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    try:
        commands = gateway.poll(payload.owner_id, limit=payload.limit)
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "commands": [
            {
                "commandId": command.command_id,
                "method": command.method,
                "params": command.params,
                "timeoutSeconds": command.timeout_seconds,
            }
            for command in commands
        ]
    }


@router.post("/result")
async def post_result(payload: ResultRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    try:
        result = gateway.post_result(
            payload.owner_id,
            payload.command_id,
            ok=payload.ok,
            result=payload.result,
            error=payload.error,
        )
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "commandId": result.command_id,
        "ok": result.ok,
        "completedAt": result.completed_at,
    }


@router.get("/health")
async def bridge_health(request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    gateway.expire_timed_out()
    return gateway.health()


@router.websocket("/ws")
async def bridge_websocket(websocket: WebSocket) -> None:
    owner_id = websocket.query_params.get("ownerId") or "qmt-bridge-ws"
    gateway = _get_gateway_from_state(websocket.app.state)
    await websocket.accept()
    try:
        gateway.register_owner(owner_id)
    except QmtBridgeOwnershipError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "code": "QMT_BRIDGE_OWNER_CONFLICT",
                "message": str(exc),
                "retryable": False,
            }
        )
        await websocket.close(code=4409)
        return

    await websocket.send_json({"type": "bridge.ready", "ownerId": owner_id})
    try:
        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type", ""))
            gateway.heartbeat(owner_id)
            if message_type == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "id": message.get("id"),
                        "ownerId": owner_id,
                    }
                )
                continue
            if message_type == "hello":
                await websocket.send_json(
                    {
                        "type": "hello.ack",
                        "id": message.get("id"),
                        "ownerId": owner_id,
                    }
                )
                continue
            await websocket.send_json(
                {
                    "type": "error",
                    "id": message.get("id"),
                    "code": "QMT_BRIDGE_WS_UNSUPPORTED_MESSAGE",
                    "message": "Unsupported QMT bridge websocket message",
                    "retryable": False,
                }
            )
    except WebSocketDisconnect:
        return
