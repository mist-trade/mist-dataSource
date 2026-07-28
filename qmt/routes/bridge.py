"""Full-QMT command bridge routes."""

from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.core.local_bridge import is_trusted_local_bridge_peer
from src.datasource.qmt.realtime.gateway import (
    QmtBridgeOwnershipError,
    QmtCommandGateway,
    QmtCommandRejectedError,
)
from src.datasource.qmt.realtime.subscription import (
    QmtNativeReply,
    QmtSubscriptionControlError,
    QmtSubscriptionController,
    QmtSubscriptionSequenceError,
)
from src.ws.health_contract import QmtBridgeHealth

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
    bridge_build_id: str = Field(alias="bridgeBuildId")
    bridge_artifact_sha256: str = Field(alias="bridgeArtifactSha256")
    bridge_runtime_fingerprint: str = Field(
        default="unknown",
        alias="bridgeRuntimeFingerprint",
    )


PositiveStrictInt = Annotated[StrictInt, Field(gt=0)]
PollLimit = Annotated[StrictInt, Field(gt=0, le=16)]
PositiveFiniteSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class PollRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    lease_token: str = Field(alias="leaseToken")
    generation: int
    limit: PollLimit = 1


class ResultRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    lease_token: str = Field(alias="leaseToken")
    generation: int
    command_id: str = Field(alias="commandId")
    ok: bool
    result: Any | None = None
    error: dict[str, Any] | None = None


class CommandRequest(BridgeModel):
    method: Literal[
        "health",
        "runtime_introspection",
        "get_market_data_ex",
        "get_stock_list_in_sector",
    ]
    params: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: PositiveFiniteSeconds | None = Field(
        default=None,
        alias="timeoutSeconds",
    )


class SubscriptionLeaseRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    lease_token: str = Field(alias="leaseToken")
    generation: StrictInt


class SubscriptionResultFailure(BridgeModel):
    symbol: str | None
    reason: str


class SubscriptionResultRequest(SubscriptionLeaseRequest):
    call_sequence: PositiveStrictInt = Field(alias="callSequence")
    success: Any | None = None
    failure: SubscriptionResultFailure | None = None

    @model_validator(mode="after")
    def validate_result_union(self) -> "SubscriptionResultRequest":
        present = {name for name in ("success", "failure") if name in self.model_fields_set}
        if len(present) != 1:
            raise ValueError("exactly one of success or failure is required")
        if "failure" in present and self.failure is None:
            raise ValueError("failure must be an object")
        return self


class SubscriptionSnapshotRequest(SubscriptionLeaseRequest):
    subscription_id: StrictInt = Field(alias="subscriptionId")
    captured_at: str = Field(alias="capturedAt")
    native: dict[str, Any]


def _get_gateway_from_state(state: Any) -> QmtCommandGateway:
    gateway = getattr(state, "qmt_command_gateway", None)
    if gateway is None:
        gateway = QmtCommandGateway()
        state.qmt_command_gateway = gateway
    return gateway


def get_gateway(request: Request) -> QmtCommandGateway:
    return _get_gateway_from_state(request.app.state)


def get_subscription_controller(request: Request) -> QmtSubscriptionController:
    controller = getattr(request.app.state, "qmt_subscription_controller", None)
    if controller is None:
        raise HTTPException(status_code=503, detail="QMT subscription control is disabled")
    return cast(QmtSubscriptionController, controller)


def _require_loopback(request: Request) -> None:
    client = request.client
    if client is None or not is_trusted_local_bridge_peer(client.host):
        raise HTTPException(status_code=403, detail="QMT subscription bridge is loopback-only")


@router.post("/commands")
async def enqueue_command(payload: CommandRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    try:
        command = gateway.enqueue(
            payload.method,
            payload.params,
            timeout_seconds=payload.timeout_seconds,
        )
    except QmtCommandRejectedError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail=exc.as_detail(),
        ) from exc
    return {
        "commandId": command.command_id,
        "method": command.method,
        "params": command.params,
        "timeoutSeconds": command.timeout_seconds,
    }


@router.get("/commands/{command_id}")
async def get_command_result(
    command_id: str, request: Request, response: Response
) -> dict[str, Any]:
    gateway = get_gateway(request)
    gateway.expire_timed_out()
    result = gateway.result_for(command_id)
    if result is None:
        state = gateway.command_state(command_id)
        if state in {"pending", "in_flight"}:
            response.status_code = 202
            return {"commandId": command_id, "status": "pending"}
        raise HTTPException(
            status_code=404,
            detail={
                "code": "QMT_COMMAND_NOT_FOUND",
                "message": "QMT command is unknown or its result has expired",
                "retryable": False,
                "details": {"commandId": command_id},
            },
        )
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
        owner = gateway.register_owner(
            payload.owner_id,
            bridge_build_id=payload.bridge_build_id,
            bridge_artifact_sha256=payload.bridge_artifact_sha256,
            bridge_runtime_fingerprint=payload.bridge_runtime_fingerprint,
        )
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ownerId": owner.owner_id,
        "registeredAt": owner.registered_at,
        "lastHeartbeatAt": owner.last_heartbeat_at,
        "leaseToken": owner.lease_token,
        "generation": owner.generation,
    }


@router.post("/poll")
async def poll_commands(payload: PollRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    try:
        commands = gateway.poll(
            payload.owner_id,
            lease_token=payload.lease_token,
            generation=payload.generation,
            limit=payload.limit,
        )
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
            lease_token=payload.lease_token,
            generation=payload.generation,
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


@router.post("/subscriptions/poll")
async def poll_subscription_command(
    payload: SubscriptionLeaseRequest,
    request: Request,
) -> dict[str, Any]:
    _require_loopback(request)
    controller = get_subscription_controller(request)
    try:
        command = controller.poll_command(
            payload.owner_id,
            payload.lease_token,
            payload.generation,
        )
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"command": command}


@router.post("/subscriptions/result")
async def post_subscription_result(
    payload: SubscriptionResultRequest,
    request: Request,
) -> dict[str, Any]:
    _require_loopback(request)
    controller = get_subscription_controller(request)
    failure = payload.failure
    reply = QmtNativeReply(
        success_present="success" in payload.model_fields_set,
        success=payload.success,
        failure=(
            {"symbol": failure.symbol, "reason": failure.reason} if failure is not None else None
        ),
    )
    try:
        controller.post_result(
            payload.owner_id,
            payload.lease_token,
            payload.generation,
            payload.call_sequence,
            reply,
        )
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QmtSubscriptionSequenceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"accepted": True}


@router.post("/subscriptions/snapshot")
async def post_subscription_snapshot(
    payload: SubscriptionSnapshotRequest,
    request: Request,
) -> dict[str, Any]:
    _require_loopback(request)
    controller = get_subscription_controller(request)
    try:
        return await controller.accept_snapshot(
            payload.owner_id,
            payload.lease_token,
            payload.generation,
            payload.subscription_id,
            payload.captured_at,
            payload.native,
        )
    except QmtBridgeOwnershipError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except QmtSubscriptionControlError as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc


@router.get("/health", response_model=QmtBridgeHealth)
async def bridge_health(request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    gateway.expire_timed_out()
    return gateway.health()
