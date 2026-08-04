"""Typed public health contracts shared by TDX and QMT applications."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BridgeHealth(BaseModel):
    """Common bridge-owner fields."""

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )

    ready: bool
    owner_id: str | None = Field(alias="ownerId")
    owner_generation: int = Field(alias="ownerGeneration", ge=0)
    bridge_build_id: str | None = Field(alias="bridgeBuildId")


class TdxBridgeHealth(BridgeHealth):
    """Typed TDX bridge-scoped diagnostics."""

    owner_age_seconds: float | None = Field(alias="ownerAgeSeconds", ge=0)
    bridge_artifact_sha256: str | None = Field(alias="bridgeArtifactSha256")
    desired_revision: int = Field(alias="desiredRevision", ge=0)
    converged_revision: int = Field(alias="convergedRevision", ge=-1)
    desired_symbols: int = Field(alias="desiredSymbols", ge=0)
    converged_symbols: int = Field(alias="convergedSymbols", ge=0)
    attempted_revision: int = Field(alias="attemptedRevision", ge=-1)
    native_probe_revision: int = Field(alias="nativeProbeRevision", ge=0)
    completed_native_probe_revision: int = Field(
        alias="completedNativeProbeRevision",
        ge=0,
    )
    reconcile_retry_attempt: int = Field(alias="reconcileRetryAttempt", ge=0)
    reconcile_retry_after_ms: int | None = Field(
        alias="reconcileRetryAfterMs",
        ge=0,
    )
    last_failure_code: str | None = Field(alias="lastFailureCode")
    last_failure_retryable: bool | None = Field(alias="lastFailureRetryable")
    last_snapshot_at: str | None = Field(alias="lastSnapshotAt")
    last_snapshot_age_seconds: float | None = Field(
        alias="lastSnapshotAgeSeconds",
        ge=0,
    )
    control_totals: list[dict[str, Any]] = Field(alias="controlTotals")


class QmtBridgeHealth(BridgeHealth):
    """Typed QMT bridge-scoped diagnostics."""

    last_heartbeat_at: float | None = Field(alias="lastHeartbeatAt")
    owner_age_seconds: float | None = Field(alias="ownerAgeSeconds", ge=0)
    owner_stale: bool = Field(alias="ownerStale")
    bridge_artifact_sha256: str | None = Field(alias="bridgeArtifactSha256")
    bridge_runtime_fingerprint: str | None = Field(alias="bridgeRuntimeFingerprint")
    pending_count: int = Field(alias="pendingCount", ge=0)
    in_flight_count: int = Field(alias="inFlightCount", ge=0)
    result_count: int = Field(alias="resultCount", ge=0)
    max_outstanding_commands: int = Field(alias="maxOutstandingCommands", ge=1)
    max_retained_results: int = Field(alias="maxRetainedResults", ge=1)
    result_ttl_seconds: float = Field(alias="resultTtlSeconds", gt=0)
    max_poll_limit: int = Field(alias="maxPollLimit", ge=1)
    max_command_bytes: int = Field(alias="maxCommandBytes", ge=1)
    max_result_bytes: int = Field(alias="maxResultBytes", ge=1)
    max_retained_result_bytes: int = Field(alias="maxRetainedResultBytes", ge=1)
    retained_result_bytes: int = Field(alias="retainedResultBytes", ge=0)
    oldest_pending_age_seconds: float | None = Field(
        alias="oldestPendingAgeSeconds",
        ge=0,
    )
    oldest_result_age_seconds: float | None = Field(
        alias="oldestResultAgeSeconds",
        ge=0,
    )
    command_rejection_totals: list["QmtCommandRejectionTotal"] = Field(
        alias="commandRejectionTotals"
    )


class QmtCommandRejectionTotal(BaseModel):
    """Fixed-cardinality QMT historical command rejection counter."""

    model_config = ConfigDict(extra="forbid")

    reason: Literal[
        "capacity",
        "command_invalid",
        "command_too_large",
        "result_capacity",
        "result_invalid",
        "result_too_large",
    ]
    value: int = Field(ge=0)


class TdxDatasourceHealth(BaseModel):
    """TDX root health with an explicit aggregate bridge boundary."""

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )

    status: Literal["ok"]
    instance: Literal["tdx"]
    realtime_mode: Literal["off", "builtin"] = Field(alias="realtimeMode")
    connections: int = Field(ge=0)
    ws_connected: bool = Field(alias="wsConnected")
    tdx_http_reachable: bool = Field(alias="tdxHttpReachable")
    last_error: str | None = Field(alias="lastError")
    bridge: TdxBridgeHealth


class QmtDatasourceHealth(BaseModel):
    """QMT root health with provider-specific state in responsibility objects."""

    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )

    status: Literal["ok"]
    instance: Literal["qmt"]
    realtime_mode: Literal["off", "builtin"] = Field(alias="realtimeMode")
    bridge: QmtBridgeHealth
    realtime: dict[str, Any]
    subscriptions: dict[str, Any]
