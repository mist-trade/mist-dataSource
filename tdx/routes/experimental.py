"""Experimental TDX builtin-bridge loopback HTTP routes.

Loopback-only (127.0.0.1 / ::1). The terminal strategy script calls these to
register ownership, poll desired subscription state, report reconcile results,
and post native snapshots.

Only mounted when ``TDX_REALTIME_MODE=builtin_experimental``.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from src.datasource.tdx.experimental_gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_DRAFT_REVISION,
    ACCEPTED_SCHEMA_VERSION,
    ExperimentalTdxRealtimeGateway,
    GatewayError,
)

router = APIRouter()


# --- request models -----------------------------------------------------


class OwnerRegisterRequest(BaseModel):
    ownerId: str
    bridgeBuildId: str
    bridgeArtifactSha256: str
    acquisitionProfile: str = ACCEPTED_ACQUISITION_PROFILE
    schemaVersion: int = ACCEPTED_SCHEMA_VERSION
    draftRevision: int = ACCEPTED_DRAFT_REVISION


class PollRequest(BaseModel):
    leaseToken: str
    appliedRevision: int = -1


class RejectedItem(BaseModel):
    symbol: str
    reason: str


class ResultRequest(BaseModel):
    leaseToken: str
    desiredRevision: int
    appliedRevision: int
    active: list[str] = Field(default_factory=lambda: list[str]())
    rejected: list[RejectedItem] = Field(default_factory=lambda: list[RejectedItem]())


class SnapshotRequest(BaseModel):
    leaseToken: str
    symbol: str
    producerSequence: int
    capturedAt: str
    native: dict[str, Any]


# --- helpers ------------------------------------------------------------


def _get_gateway(request: Request) -> ExperimentalTdxRealtimeGateway:
    gateway: ExperimentalTdxRealtimeGateway | None = getattr(
        request.app.state, "tdx_experimental_gateway", None
    )
    if gateway is None:
        raise GatewayError(
            "TDX_BRIDGE_NOT_READY", "experimental gateway not initialized", retryable=True
        )
    return gateway


def _require_loopback(request: Request) -> None:
    """Reject non-loopback connections."""
    client = request.client
    if client is None or client.host not in ("127.0.0.1", "::1", "localhost"):
        raise GatewayError(
            "TDX_BRIDGE_NOT_LOOPBACK",
            f"bridge endpoints are loopback-only (got {client.host if client else 'unknown'})",
            retryable=False,
        )


# --- routes -------------------------------------------------------------


@router.post("/tdx/bridge/owner")
async def register_owner(body: OwnerRegisterRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        return await gateway.register_owner(
            owner_id=body.ownerId,
            bridge_build_id=body.bridgeBuildId,
            bridge_artifact_sha256=body.bridgeArtifactSha256,
            acquisition_profile=body.acquisitionProfile,
            schema_version=body.schemaVersion,
            draft_revision=body.draftRevision,
        )
    except GatewayError as exc:
        return {"accepted": False, "error": {"code": exc.code, "message": exc.message}}


@router.post("/tdx/bridge/poll")
async def poll(body: PollRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        return await gateway.poll(
            lease_token=body.leaseToken, applied_revision=body.appliedRevision
        )
    except GatewayError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}


@router.post("/tdx/bridge/result")
async def post_result(body: ResultRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        return await gateway.post_result(
            lease_token=body.leaseToken,
            desired_revision=body.desiredRevision,
            applied_revision=body.appliedRevision,
            active=body.active,
            rejected=[r.model_dump() for r in body.rejected],
        )
    except GatewayError as exc:
        return {"error": {"code": exc.code, "message": exc.message}}


@router.post("/tdx/bridge/snapshot")
async def post_snapshot(body: SnapshotRequest, request: Request) -> dict[str, Any]:
    _require_loopback(request)
    gateway = _get_gateway(request)
    try:
        result = await gateway.post_snapshot(
            lease_token=body.leaseToken,
            symbol=body.symbol,
            producer_sequence=body.producerSequence,
            captured_at=body.capturedAt,
            native=body.native,
        )
        # Broadcast the typed frame on the experimental WS manager (isolated).
        from src.ws.protocol import ws_experimental_snapshot

        ws_manager = getattr(request.app.state, "tdx_experimental_ws_manager", None)
        if ws_manager is not None and result.get("accepted"):
            await ws_manager.broadcast(ws_experimental_snapshot("tdx", result["frame"]))
        return {"accepted": result["accepted"], "sequence": result["sequence"]}
    except GatewayError as exc:
        return {"accepted": False, "error": {"code": exc.code, "message": exc.message}}
    except Exception as exc:  # ExperimentalDecoderError etc.
        return {
            "accepted": False,
            "error": {"code": "TDX_BRIDGE_DECODE_ERROR", "message": str(exc)},
        }


@router.get("/tdx/bridge/health")
async def bridge_health(request: Request) -> dict[str, Any]:
    gateway = _get_gateway(request)
    return await gateway.health()


class SyncDesiredRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)


@router.post("/tdx/bridge/desired")
async def sync_desired(body: SyncDesiredRequest, request: Request) -> dict[str, Any]:
    """Set the desired subscription set (full replace).

    This is the production desired-state entry point: Mist or an operator
    calls this to tell the gateway which symbols the terminal bridge should
    subscribe to. The terminal polls this via /tdx/bridge/poll.
    """
    gateway = _get_gateway(request)
    revision = await gateway.sync_desired(body.symbols)
    return {"desiredRevision": revision, "symbolCount": len(body.symbols)}
