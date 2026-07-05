"""Full-QMT command bridge routes."""

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.datasource.qmt.command_gateway import (
    QmtBridgeOwnershipError,
    QmtCommandGateway,
)

router = APIRouter()


class BridgeModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


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


class CommandRequest(BridgeModel):
    method: Literal["health", "get_market_data_ex", "get_full_tick", "get_stock_list_in_sector"]
    params: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, alias="timeoutSeconds")


def _get_gateway_from_state(state: Any) -> QmtCommandGateway:
    gateway = getattr(state, "qmt_command_gateway", None)
    if gateway is None:
        gateway = QmtCommandGateway()
        state.qmt_command_gateway = gateway
    return gateway


def get_gateway(request: Request) -> QmtCommandGateway:
    return _get_gateway_from_state(request.app.state)


@router.post("/commands")
async def enqueue_command(payload: CommandRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    command = gateway.enqueue(
        payload.method,
        payload.params,
        timeout_seconds=payload.timeout_seconds,
    )
    return {
        "commandId": command.command_id,
        "method": command.method,
        "params": command.params,
        "timeoutSeconds": command.timeout_seconds,
    }


@router.get("/commands/{command_id}")
async def get_command_result(command_id: str, request: Request, response: Response) -> dict[str, Any]:
    gateway = get_gateway(request)
    gateway.expire_timed_out()
    result = gateway.result_for(command_id)
    if result is None:
        response.status_code = 202
        return {"commandId": command_id, "status": "pending"}
    return {
        "commandId": result.command_id,
        "ok": result.ok,
        "completedAt": result.completed_at,
        "result": result.result,
        "error": result.error,
    }


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
