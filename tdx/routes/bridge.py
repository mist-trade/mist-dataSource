"""TDX realtime builtin-bridge loopback HTTP routes.

Loopback-only (127.0.0.1 / ::1). The terminal strategy script calls these to
register ownership, poll desired subscription state, report reconcile results,
and post native snapshots.

Mounted only when ``TDX_REALTIME_MODE=builtin``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.datasource.tdx.realtime.runtime import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_SCHEMA_VERSION,
    GatewayError,
    TdxRealtimeGateway,
)
from src.ws.protocol import ws_realtime_snapshot

router = APIRouter()


# --- request models -----------------------------------------------------


class StrictRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OwnerRegisterRequest(StrictRequestModel):
    ownerId: str
    mode: str  # Golden requires mode in owner registration.
    bridgeBuildId: str
    bridgeArtifactSha256: str
    acquisitionProfile: str = ACCEPTED_ACQUISITION_PROFILE
    schemaVersion: int = ACCEPTED_SCHEMA_VERSION


class PollRequest(StrictRequestModel):
    leaseToken: str
    streamEpoch: str  # Golden requires streamEpoch in subsequent requests.
    appliedRevision: int = -1


class RejectedItem(StrictRequestModel):
    symbol: str
    reason: str
    code: str = "TDX_BRIDGE_NATIVE_REJECTED"
    retryable: bool = True


class ResultRequest(StrictRequestModel):
    leaseToken: str
    streamEpoch: str  # Golden requires streamEpoch.
    desiredRevision: int
    appliedRevision: int
    active: list[str] = Field(default_factory=lambda: list[str]())
    rejected: list[RejectedItem] = Field(default_factory=lambda: list[RejectedItem]())


class SnapshotRequest(StrictRequestModel):
    leaseToken: str
    streamEpoch: str  # Golden requires streamEpoch.
    symbol: str
    producerSequence: int
    capturedAt: str
    native: dict[str, Any]


# --- helpers ------------------------------------------------------------


def _get_gateway(request: Request) -> TdxRealtimeGateway:
    gateway: TdxRealtimeGateway | None = getattr(
        request.app.state, "tdx_realtime_gateway", None
    )
    if gateway is None:
        raise GatewayError(
            "TDX_BRIDGE_NOT_READY", "realtime gateway not initialized", retryable=True
        )
    return gateway


def _require_loopback(request: Request) -> None:
    """Reject non-loopback connections."""
    client = request.client
    if client is None or client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "TDX_BRIDGE_NOT_LOOPBACK",
                "message": "bridge endpoints are loopback-only",
                "retryable": False,
            },
        )


def _gateway_error(exc: GatewayError) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": exc.code,
        "message": exc.message,
        "retryable": exc.retryable,
    }
    if exc.retry_after_ms is not None:
        error["retryAfterMs"] = exc.retry_after_ms
    return error


# --- routes -------------------------------------------------------------


@router.post("/tdx/bridge/owner")
async def register_owner(body: OwnerRegisterRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        if body.mode != "builtin":
            raise GatewayError(
                "TDX_BRIDGE_MODE_MISMATCH",
                f"owner mode must be 'builtin' (got {body.mode!r})",
                retryable=False,
            )
        return await gateway.register_owner(
            owner_id=body.ownerId,
            bridge_build_id=body.bridgeBuildId,
            bridge_artifact_sha256=body.bridgeArtifactSha256,
            acquisition_profile=body.acquisitionProfile,
            schema_version=body.schemaVersion,
        )
    except GatewayError as exc:
        return {"accepted": False, "error": _gateway_error(exc)}


@router.post("/tdx/bridge/poll")
async def poll(body: PollRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        return await gateway.poll(
            lease_token=body.leaseToken,
            stream_epoch=body.streamEpoch,
            applied_revision=body.appliedRevision,
        )
    except GatewayError as exc:
        return {"error": _gateway_error(exc)}


@router.post("/tdx/bridge/result")
async def post_result(body: ResultRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        return await gateway.post_result(
            lease_token=body.leaseToken,
            stream_epoch=body.streamEpoch,
            desired_revision=body.desiredRevision,
            applied_revision=body.appliedRevision,
            active=body.active,
            rejected=[r.model_dump() for r in body.rejected],
        )
    except GatewayError as exc:
        return {"error": _gateway_error(exc)}


@router.post("/tdx/bridge/snapshot")
async def post_snapshot(body: SnapshotRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        result = await gateway.post_snapshot(
            lease_token=body.leaseToken,
            stream_epoch=body.streamEpoch,
            symbol=body.symbol,
            producer_sequence=body.producerSequence,
            captured_at=body.capturedAt,
            native=body.native,
        )
        # Broadcast the validated native frame on the realtime WS manager.
        ws_manager = getattr(request.app.state, "tdx_realtime_ws_manager", None)
        if ws_manager is not None and result.get("accepted"):
            await ws_manager.broadcast(ws_realtime_snapshot("tdx", result["frame"]))
        return {"accepted": result["accepted"], "sequence": result["sequence"]}
    except GatewayError as exc:
        return {"accepted": False, "error": _gateway_error(exc)}
    except Exception as exc:  # Native validation error etc.
        return {
            "accepted": False,
            "error": {"code": "TDX_BRIDGE_DECODE_ERROR", "message": str(exc)},
        }


@router.get("/tdx/bridge/health")
async def bridge_health(request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    return await gateway.health()


@router.get("/tdx/bridge/evidence/{symbol}")
async def bridge_native_evidence(symbol: str, request: Request) -> dict[str, Any]:
    """Return bounded native HIL evidence without owner credentials."""
    _require_loopback(request)
    if request.query_params:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "TDX_BRIDGE_EVIDENCE_UNKNOWN_FIELDS",
                "message": "native evidence accepts no query fields",
                "retryable": False,
                "fields": sorted(request.query_params.keys()),
            },
        )
    gateway = _get_gateway(request)
    try:
        return await gateway.read_native_evidence(symbol)
    except GatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_gateway_error(exc),
        ) from exc
