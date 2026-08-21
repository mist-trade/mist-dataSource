"""TDX realtime builtin-bridge loopback HTTP routes.

Loopback-only (127.0.0.1 / ::1). The terminal strategy script calls these to
register ownership, poll desired subscription state, report reconcile results,
and post native snapshots.

Mounted only when ``TDX_REALTIME_MODE=builtin``.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from src.core.local_bridge import is_trusted_local_bridge_peer
from src.core.logging import get_logger
from src.datasource import metrics as ds_metrics
from src.datasource.tdx.realtime.gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_SCHEMA_VERSION,
    GatewayError,
    TdxRealtimeGateway,
)
from src.ws.health_contract import TdxBridgeHealth
from src.ws.protocol import ws_realtime_snapshot

_log = get_logger(__name__)

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
    nativeProbeRevision: int = 0
    active: list[str] = Field(default_factory=lambda: list[str]())
    rejected: list[RejectedItem] = Field(default_factory=lambda: list[RejectedItem]())


class SnapshotRequest(StrictRequestModel):
    leaseToken: str
    streamEpoch: str  # Golden requires streamEpoch.
    symbol: str
    capturedAt: str
    native: dict[str, Any] = Field(
        description=(
            "Complete provider-native TDX snapshot. When present, exact Volume and "
            "Amount keys must contain unsigned ASCII decimal strings with scale <= 8."
        )
    )


class ObservabilityRequest(StrictRequestModel):
    """Bridge-side counters for E-0 throughput observation (no OTel in terminal)."""

    leaseToken: str
    streamEpoch: str
    intervalSeconds: float = 30.0
    counters: dict[str, float]
    sender: dict[str, Any] | None = None


# --- helpers ------------------------------------------------------------


def _get_gateway(request: Request) -> TdxRealtimeGateway:
    gateway: TdxRealtimeGateway | None = getattr(request.app.state, "tdx_realtime_gateway", None)
    if gateway is None:
        raise GatewayError(
            "TDX_BRIDGE_NOT_READY", "realtime gateway not initialized", retryable=True
        )
    return gateway


def _require_loopback(request: Request) -> None:
    """Reject peers outside native loopback or the explicit Docker host gateway."""
    client = request.client
    if client is None or not is_trusted_local_bridge_peer(client.host):
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
            native_probe_revision=body.nativeProbeRevision,
        )
    except GatewayError as exc:
        return {"error": _gateway_error(exc)}


@router.post("/tdx/bridge/snapshot")
async def post_snapshot(body: SnapshotRequest, request: Request) -> dict[str, Any]:
    try:
        _require_loopback(request)
    except HTTPException:
        ds_metrics.record_snapshot_rejected("tdx", "not_loopback")
        _log.warning("ingest reject source=tdx reason=not_loopback")
        raise
    try:
        gateway = _get_gateway(request)
    except GatewayError:
        ds_metrics.record_snapshot_rejected("tdx", "not_ready")
        _log.warning("ingest reject source=tdx reason=not_ready")
        raise
    try:
        result = await gateway.post_snapshot(
            lease_token=body.leaseToken,
            stream_epoch=body.streamEpoch,
            symbol=body.symbol,
            captured_at=body.capturedAt,
            native=body.native,
        )
        # Broadcast the validated native frame on the realtime WS manager.
        ws_manager = getattr(request.app.state, "tdx_realtime_ws_manager", None)
        if ws_manager is not None and result.get("accepted"):
            _log.info(
                "broadcast source=tdx clients=%d",
                ws_manager.connection_count,
            )
            ds_metrics.set_ws_clients("tdx", ws_manager.connection_count)
            await ws_manager.broadcast(ws_realtime_snapshot("tdx", result["frame"]))
        return {}
    except GatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_gateway_error(exc),
        ) from exc
    except Exception as exc:  # Native validation error etc.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "TDX_BRIDGE_DECODE_ERROR", "message": str(exc)},
        ) from exc


@router.post("/tdx/bridge/observability")
async def post_observability(
    body: ObservabilityRequest, request: Request
) -> dict[str, Any]:
    """Accept bridge-side counters (E-0) and surface them as a log line.

    The terminal bridge has no OTel SDK; this endpoint is its observability
    channel into the datasource's OpenObserve log stream.
    """
    _require_loopback(request)
    gateway = _get_gateway(request)
    # Validate the owner identity so a stray peer cannot inject counters.
    if not await gateway.owner_matches(body.leaseToken, body.streamEpoch):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_gateway_error(
                GatewayError(
                    "TDX_BRIDGE_OWNER_MISMATCH",
                    "observability lease/epoch does not match the active owner",
                    retryable=False,
                )
            ),
        )
    _log.info(
        "bridge observability source=tdx interval=%s counters=%s sender=%s",
        body.intervalSeconds,
        json.dumps(body.counters, sort_keys=True),
        json.dumps(body.sender, sort_keys=True) if body.sender else "none",
    )
    # Feed bridge counters into the recovery state machine as auxiliary
    # activity signal (best-effort; counters is a typed dict[str, float]).
    counters = body.counters
    await gateway.observe_bridge_activity(
        callback_count=int(counters["callback_count"]) if "callback_count" in counters else None,
        fetch_count=int(counters["fetch_count"]) if "fetch_count" in counters else None,
    )
    return {"accepted": True}


@router.get("/tdx/bridge/health", response_model=TdxBridgeHealth)
async def bridge_health(request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    return await gateway.health()

