"""Full-QMT command bridge routes."""

from datetime import datetime
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from src.datasource.qmt.bridge import (
    QmtBridgeOwnershipError,
    QmtCommandGateway,
)

router = APIRouter()

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
REALTIME_COMMAND_METHODS = {"get_full_tick"}
CN_REALTIME_MARKETS = {"SH", "SZ", "BJ"}
HK_REALTIME_MARKETS = {"HK"}


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


class PollRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    lease_token: str = Field(alias="leaseToken")
    generation: int
    limit: int = 1


class ResultRequest(BridgeModel):
    owner_id: str = Field(alias="ownerId")
    lease_token: str = Field(alias="leaseToken")
    generation: int
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


def _bridge_now(request: Request) -> datetime:
    clock = getattr(request.app.state, "qmt_bridge_now", None)
    now_value = datetime.now(BEIJING_TZ)
    if callable(clock):
        candidate = clock()
        if isinstance(candidate, datetime):
            now_value = candidate
    if now_value.tzinfo is None:
        return now_value.replace(tzinfo=BEIJING_TZ)
    return now_value.astimezone(BEIJING_TZ)


def _is_realtime_trading_session(now: datetime, symbols: list[str]) -> bool:
    if now.weekday() >= 5:
        return False
    markets = _markets_from_symbols(symbols)
    return any(_is_market_realtime_session(now, market) for market in markets)


def _markets_from_symbols(symbols: list[str]) -> set[str]:
    markets: set[str] = set()
    for symbol in symbols:
        text = str(symbol).upper().strip()
        if "." not in text:
            continue
        suffix = text.rsplit(".", 1)[1]
        if suffix in CN_REALTIME_MARKETS:
            markets.add("CN")
        elif suffix in HK_REALTIME_MARKETS:
            markets.add("HK")
    return markets or {"UNKNOWN"}


def _is_market_realtime_session(now: datetime, market: str) -> bool:
    minute_of_day = now.hour * 60 + now.minute
    if market == "CN":
        return _in_minutes(minute_of_day, 9, 15, 11, 35) or _in_minutes(
            minute_of_day, 13, 0, 15, 5
        )
    if market == "HK":
        return _in_minutes(minute_of_day, 9, 0, 12, 5) or _in_minutes(
            minute_of_day, 13, 0, 16, 10
        )
    return _in_minutes(minute_of_day, 9, 0, 16, 10)


def _in_minutes(
    value: int,
    start_hour: int,
    start_minute: int,
    end_hour: int,
    end_minute: int,
) -> bool:
    start = start_hour * 60 + start_minute
    end = end_hour * 60 + end_minute
    return start <= value <= end


@router.post("/commands")
async def enqueue_command(payload: CommandRequest, request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    if payload.method in REALTIME_COMMAND_METHODS:
        now = _bridge_now(request)
        symbols = _symbols_from_params(payload.params)
        if not _is_realtime_trading_session(now, symbols):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "QMT_REALTIME_OUTSIDE_TRADING_SESSION",
                    "message": "QMT realtime bridge command is outside market trading session",
                    "retryable": True,
                    "details": {
                        "method": payload.method,
                        "markets": sorted(_markets_from_symbols(symbols)),
                        "symbols": symbols,
                        "beijingTime": now.isoformat(),
                    },
                },
            )
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


def _symbols_from_params(params: dict[str, Any]) -> list[str]:
    value = params.get("symbols", [])
    if isinstance(value, list):
        return [str(item) for item in cast(list[Any], value)]
    return []


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
        owner = gateway.register_owner(
            payload.owner_id,
            bridge_build_id=payload.bridge_build_id,
            bridge_artifact_sha256=payload.bridge_artifact_sha256,
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


@router.get("/health")
async def bridge_health(request: Request) -> dict[str, Any]:
    gateway = get_gateway(request)
    gateway.expire_timed_out()
    return gateway.health()
