"""TDX realtime control-plane gateway.

Control-plane authority for the builtin-bridge pathway. Owns:
- single-owner lease (with opaque token + stale eviction)
- four-state subscription convergence (desired / attempted / converged /
  observedNative) under a stable owner epoch
- native subscription reconciliation

This is rewritten from scratch. The remote WIP branch
(``codex/tdx-builtin-realtime-bridge``) was used only as route/test scaffold
reference; its state machine had structural defects (no lease/epoch/build,
result advances on error, snapshot checks desired not converged, sequence
committed after await).

Data-plane snapshot validation lives in ``realtime_native_validator``. This gateway
is transport/control only — it does not interpret price semantics.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, cast

from opentelemetry import trace

from src.core.logging import get_logger
from src.datasource import metrics as ds_metrics
from src.datasource.realtime.stall_detector import ActivityWindow, StallDetector
from src.datasource.realtime_native_safety import validate_native_payload_safety
from src.datasource.tdx.market_normalization import dedupe_normalized_symbols, dedupe_stable
from src.datasource.tdx.realtime.contract import (
    validate_tdx_realtime_native_snapshot,
)

_log = get_logger(__name__)
_tracer = trace.get_tracer("mist-datasource")

# Contract tuple accepted by this gateway build.
ACCEPTED_PAYLOAD_TYPE = "mist.realtime.native_snapshot"
ACCEPTED_SCHEMA_VERSION = 2
ACCEPTED_ACQUISITION_PROFILE = "tdx.get_market_snapshot"

#: Owner stale after this many seconds without a poll/heartbeat.
OWNER_STALE_AFTER_SECONDS = 10.0
#: A different owner that retries continuously may replace a fresh owner after
#: this grace period. The old lease is fenced immediately after replacement.
OWNER_TAKEOVER_GRACE_SECONDS = 5.0
OWNER_TAKEOVER_RETRY_WINDOW_SECONDS = 2.5
#: Subscription reconcile batch size.
RECONCILE_BATCH = 50
RECONCILE_RETRY_BASE_MS = 250
RECONCILE_RETRY_MAX_MS = 5_000

_RFC3339_PATTERN = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"T(?P<hour>[01]\d|2[0-3]):(?P<minute>[0-5]\d):(?P<second>[0-5]\d)"
    r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


class GatewayError(Exception):
    """Base gateway error."""

    def __init__(
        self,
        code: str,
        message: str,
        retryable: bool = False,
        retry_after_ms: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.retry_after_ms = retry_after_ms


@dataclass
class BridgeOwner:
    """Registered terminal bridge owner."""

    owner_id: str
    lease_token: str
    stream_epoch: str
    bridge_build_id: str
    bridge_artifact_sha256: str
    acquisition_profile: str
    schema_version: int
    last_seen_monotonic: float
    generation: int  # increments each owner registration


@dataclass
class _OwnerTakeoverCandidate:
    fingerprint: tuple[str, str, str, str, int]
    first_seen_monotonic: float
    last_seen_monotonic: float


@dataclass
class TdxRealtimeGateway:
    """Control-plane gateway for the TDX builtin bridge."""

    max_subscriptions: int = 100
    control_timeout_seconds: float = 10.0
    _owner: BridgeOwner | None = None
    _owner_generation_counter: int = 0
    _takeover_candidate: _OwnerTakeoverCandidate | None = None
    _retired_owner_ids: set[str] = field(default_factory=lambda: set[str]())
    # Desired subscription set (revisioned).
    _desired_symbols: list[str] = field(default_factory=lambda: list[str]())
    _desired_revision: int = 0
    # Four-state convergence.
    _attempted_revision: int = -1
    _converged_revision: int = -1
    _observed_native_symbols: set[str] = field(default_factory=lambda: set[str]())
    # Last active set reported by terminal (used for reconcile diff in poll).
    # This is SEPARATE from _observed_native_symbols (converged set): it persists
    # across desired-revision changes so unsubscribe can be computed correctly.
    _last_reported_active: set[str] = field(default_factory=lambda: set[str]())
    # Datasource-private read barrier. A get_subscriptions request increments
    # this revision and waits until the terminal reports a native list probe
    # carrying the same (or a later) revision.
    _native_probe_revision: int = 0
    _completed_native_probe_revision: int = 0
    # Accumulated accepted/rejected native symbols from the last result.
    _last_applied_active: list[str] = field(default_factory=lambda: list[str]())
    _last_rejected: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    _reconcile_retry_attempt: int = 0
    _reconcile_retry_after_monotonic: float | None = None
    _last_retryable: bool | None = None
    _last_failure_code: str | None = None
    _last_snapshot_monotonic: float | None = None
    _last_snapshot_at: str | None = None
    # Subscription recovery state machine (spec realtime-subscription-restart-recovery).
    _stall: StallDetector = field(
        default_factory=lambda: StallDetector(source="tdx", window=ActivityWindow())
    )
    _stall_tick_seconds: float = 5.0
    _last_cb_count: int | None = None
    # Async lock for state transitions.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _mutation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _convergence_changed: asyncio.Event = field(default_factory=asyncio.Event)
    _control_counts: dict[tuple[str, str, str], int] = field(
        default_factory=lambda: dict[tuple[str, str, str], int]()
    )
    # --- owner / lease -------------------------------------------------

    async def register_owner(
        self,
        *,
        owner_id: str,
        bridge_build_id: str,
        bridge_artifact_sha256: str,
        acquisition_profile: str,
        schema_version: int,
    ) -> dict[str, Any]:
        """Register (or replace) the terminal owner. Returns lease info."""
        self._validate_contract_tuple(
            acquisition_profile=acquisition_profile,
            schema_version=schema_version,
        )
        async with self._lock:
            now = time.monotonic()
            if owner_id in self._retired_owner_ids:
                raise GatewayError(
                    "TDX_BRIDGE_OWNER_RETIRED",
                    f"owner {owner_id!r} was replaced by a newer bridge instance",
                    retryable=False,
                )
            # A continuously retrying new process may replace a fresh owner
            # after a short grace period. This handles TDX restarts that leave
            # the old external TPyth process alive without permitting an
            # immediate one-shot eviction.
            if self._owner is not None and self._is_owner_fresh():
                existing = self._owner
                if existing.owner_id != owner_id:
                    fingerprint = (
                        owner_id,
                        bridge_build_id,
                        bridge_artifact_sha256,
                        acquisition_profile,
                        schema_version,
                    )
                    candidate = self._takeover_candidate
                    if (
                        candidate is None
                        or candidate.fingerprint != fingerprint
                        or now - candidate.last_seen_monotonic
                        > OWNER_TAKEOVER_RETRY_WINDOW_SECONDS
                    ):
                        candidate = _OwnerTakeoverCandidate(
                            fingerprint=fingerprint,
                            first_seen_monotonic=now,
                            last_seen_monotonic=now,
                        )
                        self._takeover_candidate = candidate
                    else:
                        candidate.last_seen_monotonic = now

                    takeover_age = now - candidate.first_seen_monotonic
                    if takeover_age < OWNER_TAKEOVER_GRACE_SECONDS:
                        remaining_ms = max(
                            1,
                            int((OWNER_TAKEOVER_GRACE_SECONDS - takeover_age) * 1000),
                        )
                        raise GatewayError(
                            "TDX_BRIDGE_OWNER_ACTIVE",
                            f"another fresh owner {existing.owner_id!r} is active; "
                            f"replacement pending for {owner_id!r}",
                            retryable=True,
                            retry_after_ms=min(remaining_ms, 1_000),
                        )
                    self._retired_owner_ids.add(existing.owner_id)
            self._takeover_candidate = None
            prev_generation = self._owner.generation if self._owner is not None else 0
            prev_owner_id = self._owner.owner_id if self._owner is not None else None
            self._owner_generation_counter += 1
            generation = self._owner_generation_counter
            owner_changed = prev_owner_id != owner_id
            _log.info(
                "bridge re-registered source=tdx gen=%d->%d ownerId=%r ownerChanged=%s",
                prev_generation,
                generation,
                owner_id,
                owner_changed,
            )
            ds_metrics.record_owner_registration("tdx", owner_changed)
            stream_epoch = self._new_stream_epoch(owner_id, generation)
            lease_token = self._new_lease_token()
            self._owner = BridgeOwner(
                owner_id=owner_id,
                lease_token=lease_token,
                stream_epoch=stream_epoch,
                bridge_build_id=bridge_build_id,
                bridge_artifact_sha256=bridge_artifact_sha256,
                acquisition_profile=acquisition_profile,
                schema_version=schema_version,
                last_seen_monotonic=time.monotonic(),
                generation=generation,
            )
            # New generation resets convergence.
            self._attempted_revision = -1
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._last_reported_active = set()
            self._completed_native_probe_revision = 0
            self._reset_reconcile_retry_locked()
            self._last_snapshot_monotonic = None
            self._last_snapshot_at = None
            result = {
                "leaseToken": lease_token,
                "streamEpoch": stream_epoch,
                "generation": generation,
                "acceptedContractTuple": {
                    "payloadType": ACCEPTED_PAYLOAD_TYPE,
                    "schemaVersion": ACCEPTED_SCHEMA_VERSION,
                    "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
                },
            }
        return result

    def _validate_contract_tuple(
        self, *, acquisition_profile: str, schema_version: int
    ) -> None:
        if (
            acquisition_profile != ACCEPTED_ACQUISITION_PROFILE
            or schema_version != ACCEPTED_SCHEMA_VERSION
        ):
            raise GatewayError(
                "TDX_BRIDGE_CONTRACT_MISMATCH",
                f"contract tuple mismatch: got (acquisitionProfile={acquisition_profile},"
                f" schemaVersion={schema_version})",
                retryable=False,
            )

    @staticmethod
    def _new_stream_epoch(owner_id: str, generation: int) -> str:
        # Include a high-resolution timestamp so epoch is globally unique across
        # process restarts (counter resets to 0 on restart).
        ts = f"{time.time_ns()}"
        return f"{owner_id}-gen-{generation}-{ts}"

    @staticmethod
    def _new_lease_token() -> str:
        return f"lease-{secrets.token_urlsafe(24)}"

    # --- subscription control -----------------------------------------

    async def sync_desired(self, symbols: list[str]) -> int:
        """Set the desired subscription set (full replace). Returns new revision.

        Immediately invalidates convergence: a new revision means the old
        observedNative set is stale until the terminal reports a matching result.
        """
        cleaned = dedupe_normalized_symbols(symbols)[: self.max_subscriptions]
        async with self._lock:
            if cleaned == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = cleaned
            self._desired_revision += 1
            # Invalidate convergence: old observedNative is stale for the new revision.
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._reset_reconcile_retry_locked()
            self._convergence_changed.set()
            return self._desired_revision

    async def add_desired(self, symbols: list[str]) -> int:
        cleaned = dedupe_normalized_symbols(symbols)
        async with self._lock:
            merged = dedupe_stable([*self._desired_symbols, *cleaned])[: self.max_subscriptions]
            if merged == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = merged
            self._desired_revision += 1
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._reset_reconcile_retry_locked()
            self._convergence_changed.set()
            return self._desired_revision

    async def remove_desired(self, symbols: list[str]) -> int:
        to_remove = set(dedupe_normalized_symbols(symbols))
        async with self._lock:
            merged = [s for s in self._desired_symbols if s not in to_remove]
            if merged == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = merged
            self._desired_revision += 1
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._reset_reconcile_retry_locked()
            self._convergence_changed.set()
            return self._desired_revision

    # --- poll / result ------------------------------------------------

    async def poll(
        self,
        *,
        lease_token: str,
        stream_epoch: str,
        applied_revision: int = -1,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Terminal polls for desired state."""
        async with self._lock:
            owner = self._require_owner_epoch_locked(lease_token, stream_epoch)
            owner.last_seen_monotonic = time.monotonic()
            retry_after_ms = self._remaining_retry_ms_locked()
            return {
                "desiredRevision": self._desired_revision,
                "desiredSymbols": list(self._desired_symbols),
                "streamEpoch": owner.stream_epoch,
                "nativeProbeRevision": self._native_probe_revision,
                # Reconcile instructions based on _last_reported_active (what the
                # terminal actually has), NOT _observed_native_symbols (converged set
                # which is cleared on desired change). This ensures unsubscribe is
                # correctly computed even after desired shrinks.
                "unsubscribe": [
                    s for s in self._last_reported_active if s not in self._desired_symbols
                ],
                "subscribe": (
                    # PUSHING: full re-issue of desired (bridge re-subscribes all
                    # symbol — recovery substrate). Otherwise incremental diff.
                    list(self._desired_symbols)
                    if self._stall.push_state == "pushing"
                    else [
                        s for s in self._desired_symbols if s not in self._last_reported_active
                    ]
                ),
                "retryAfterMs": retry_after_ms,
            }

    async def post_result(
        self,
        *,
        lease_token: str,
        stream_epoch: str,
        desired_revision: int,
        applied_revision: int,
        active: list[str],
        rejected: list[dict[str, Any]],
        native_probe_revision: int = 0,
    ) -> dict[str, Any]:
        """Terminal reports reconcile outcome (four-state convergence)."""
        async with self._lock:
            owner = self._require_owner_epoch_locked(lease_token, stream_epoch)
            owner.last_seen_monotonic = time.monotonic()
            # Stale revision gate: ignore results for revisions other than current desired.
            if desired_revision != self._desired_revision:
                return {
                    "converged": False,
                    "convergedRevision": self._converged_revision,
                    "failureCode": "TDX_BRIDGE_STALE_DESIRED_REVISION",
                    "retryable": True,
                    "retryAfterMs": RECONCILE_RETRY_BASE_MS,
                }
            self._attempted_revision = desired_revision
            self._last_applied_active = dedupe_normalized_symbols(active)
            self._last_reported_active = set(self._last_applied_active)
            if (
                type(native_probe_revision) is int
                and 0 <= native_probe_revision <= self._native_probe_revision
            ):
                self._completed_native_probe_revision = max(
                    self._completed_native_probe_revision,
                    native_probe_revision,
                )
            self._last_rejected = rejected
            desired_set = set(self._desired_symbols)
            active_set = set(self._last_applied_active)
            retry_after_ms = 0
            # applied_revision must match desired_revision (sanity: terminal applied what it polled).
            converged = (
                applied_revision == desired_revision
                and len(rejected) == 0
                and active_set == desired_set
            )
            if converged:
                self._converged_revision = desired_revision
                self._observed_native_symbols = active_set
                self._reset_reconcile_retry_locked()
            else:
                # On non-convergence, clear observedNative so stale symbols
                # can no longer post snapshots until convergence is re-achieved.
                self._observed_native_symbols = set()
                retryable = all(bool(item.get("retryable", True)) for item in rejected)
                failure_code = next(
                    (str(item.get("code")) for item in rejected if item.get("code")),
                    ("TDX_BRIDGE_NATIVE_REJECTED" if rejected else "TDX_BRIDGE_RECONCILE_MISMATCH"),
                )
                self._last_retryable = retryable
                self._last_failure_code = failure_code
                if retryable:
                    self._reconcile_retry_attempt += 1
                    retry_after_ms = min(
                        RECONCILE_RETRY_BASE_MS * (2 ** (self._reconcile_retry_attempt - 1)),
                        RECONCILE_RETRY_MAX_MS,
                    )
                    self._reconcile_retry_after_monotonic = time.monotonic() + retry_after_ms / 1000
                else:
                    retry_after_ms = 0
                    self._reconcile_retry_after_monotonic = None
            self._convergence_changed.set()
            return {
                "converged": converged,
                "convergedRevision": self._converged_revision,
                "failureCode": None if converged else self._last_failure_code,
                "retryable": None if converged else self._last_retryable,
                "retryAttempt": self._reconcile_retry_attempt,
                "retryAfterMs": 0 if converged else retry_after_ms,
            }

    # --- snapshot ingestion -------------------------------------------

    async def post_snapshot(
        self,
        *,
        lease_token: str,
        stream_epoch: str,
        symbol: str,
        captured_at: str,
        native: dict[str, Any],
    ) -> dict[str, Any]:
        """Accept one flat TDX native snapshot and wrap it in schema-v2."""
        with _tracer.start_as_current_span("tdx.snapshot.ingest") as span:
            span.set_attribute("symbol", symbol)
            span.set_attribute("captured_at", captured_at)
            _log.info(
                "ingest start source=tdx symbol=%s capturedAt=%s",
                symbol,
                captured_at,
            )
            try:
                # Validate captured_at is RFC3339 (reject non-conforming timestamps).
                self._validate_rfc3339(captured_at, field_name="capturedAt")
                # Strictly validate the native object before preserving it on the wire.
                validate_native_payload_safety(native)
                validate_tdx_realtime_native_snapshot(symbol, native, expected_code=symbol)
                # All state access under lock.
                async with self._lock:
                    owner = self._require_owner_epoch_locked(lease_token, stream_epoch)
                    owner.last_seen_monotonic = time.monotonic()
                    if symbol not in self._observed_native_symbols:
                        raise GatewayError(
                            "TDX_BRIDGE_SYMBOL_NOT_CONVERGED",
                            f"{symbol} not in converged subscription set",
                            retryable=False,
                        )
                    frame = self._build_wire_frame(
                        symbol=symbol,
                        captured_at=captured_at,
                        native=native,
                    )
                    self._last_snapshot_monotonic = time.monotonic()
                    self._last_snapshot_at = dt.datetime.now(dt.UTC).isoformat()
                    self._stall.observe_snapshot()
            except GatewayError as exc:
                span.add_event("rejected", {"reason": exc.code})
                span.set_status(trace.StatusCode.ERROR, exc.code)
                _log.warning(
                    "ingest reject source=tdx reason=%s symbol=%s",
                    exc.code,
                    symbol,
                )
                ds_metrics.record_snapshot_rejected("tdx", exc.code)
                raise
            except Exception as exc:  # native validation errors etc.
                span.add_event("rejected", {"reason": "native_invalid"})
                span.set_status(trace.StatusCode.ERROR, "native_invalid")
                _log.warning(
                    "ingest reject source=tdx reason=native_invalid symbol=%s error=%s",
                    symbol,
                    exc,
                )
                ds_metrics.record_snapshot_rejected("tdx", "native_invalid")
                raise
            span.add_event("frame_built", {"schema": 2})
            span.set_status(trace.StatusCode.OK)
            _log.info(
                "frame built source=tdx symbol=%s frame_schema=2",
                symbol,
            )
            ds_metrics.record_snapshot_accepted("tdx")
            return {"accepted": True, "frame": frame}

    async def observe_bridge_activity(
        self,
        *,
        callback_count: int | None = None,
        fetch_count: int | None = None,
    ) -> None:
        """Feed bridge observability counters as auxiliary activity signal.

        Called from the observability route/frame handler. Only a moving
        callback counter is treated as activity (a frozen counter is not).
        This is best-effort: a missing/None counter advances nothing.
        """
        del fetch_count  # reserved auxiliary signal (not a stall sign on its own)
        if callback_count is not None and callback_count != self._last_cb_count:
            self._last_cb_count = callback_count
            self._stall.observe_callback()

    async def run_stall_watchdog(self) -> None:
        """Subscription recovery watchdog (in-process, no process restart).

        Recovery rounds are counted per tick (default 5s): PUSHING keeps the
        poll returning the full desired set (bridge re-subscribes), and each
        tick counts one recovery round towards escalation.
        """
        while True:
            await asyncio.sleep(self._stall_tick_seconds)
            was_escalated = self._stall.stall_escalated
            self._stall.evaluate()
            if self._stall.push_state == "pushing":
                self._stall.note_recovery()
            ds_metrics.set_stall_active("tdx", self._stall.stall_detected)
            if self._stall.stall_escalated and not was_escalated:
                ds_metrics.record_stall("tdx", "escalated")
                _log.error(
                    "subscription stall escalated source=tdx state=%s "
                    "grace=%ss maxCycles=%d cyclesDone=%d; no auto-restart",
                    self._stall.push_state,
                    self._stall.grace_seconds,
                    self._stall.max_recovery_cycles,
                    self._stall.recovery_cycles_done,
                )

    @staticmethod
    def _validate_rfc3339(value: str, *, field_name: str) -> None:
        """Strict RFC3339 validation: require date-time WITH timezone offset.

        Rejects pure dates ("2026-07-17") and offset-less times
        ("2026-07-17T14:30:00"). This is stricter than normalize_beijing_iso
        (which fills missing offset with Beijing TZ) — the realtime gateway
        requires the terminal to provide a complete timestamp.
        """
        stripped = value
        if _RFC3339_PATTERN.fullmatch(stripped) is None:
            raise GatewayError(
                "TDX_BRIDGE_INVALID_TIMESTAMP",
                f"{field_name} is not strict RFC3339: {value!r}",
                retryable=False,
            )
        try:
            dt.datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except (ValueError, TypeError) as exc:
            raise GatewayError(
                "TDX_BRIDGE_INVALID_TIMESTAMP",
                f"{field_name} is not a valid RFC3339 timestamp: {value!r}",
                retryable=False,
            ) from exc

    def _build_wire_frame(
        self,
        *,
        symbol: str,
        captured_at: str,
        native: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schemaVersion": ACCEPTED_SCHEMA_VERSION,
            "capturedAt": captured_at,
            "native": {symbol: copy.deepcopy(native)},
        }

    # --- backend-facing subscription control -------------------------

    async def execute_control(
        self,
        operation: str,
        *,
        symbol: str | None = None,
        symbols: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        response_type = {
            "sync_subscriptions": "subscriptions_synced",
            "subscribe": "subscribed",
            "unsubscribe": "unsubscribed",
            "get_subscriptions": "subscriptions",
        }.get(operation)
        if response_type is None:
            raise ValueError(f"unsupported TDX subscription operation: {operation}")

        if operation == "get_subscriptions":
            async with self._lock:
                if not self._is_owner_fresh():
                    return self._record_control(
                        operation,
                        response_type,
                        {
                            "failure": {
                                "symbol": None,
                                "reason": "TDX_SUBSCRIPTIONS_READ_FAILED",
                            }
                        },
                    )
                self._native_probe_revision += 1
                requested_probe_revision = self._native_probe_revision
                self._convergence_changed.set()
            if not await self._wait_for_native_probe(requested_probe_revision):
                return self._record_control(
                    operation,
                    response_type,
                    {
                        "failure": {
                            "symbol": None,
                            "reason": "TDX_SUBSCRIPTIONS_READ_FAILED",
                        }
                    },
                )
            async with self._lock:
                active = sorted(self._last_reported_active)
            return self._record_control(
                operation,
                response_type,
                {"success": active},
            )

        if self._mutation_lock.locked():
            return self._record_control(
                operation,
                response_type,
                {
                    "failure": {
                        "symbol": symbol,
                        "reason": "TDX_SUBSCRIPTION_CONTROL_BUSY",
                    }
                },
            )
        async with self._mutation_lock:
            if operation == "subscribe":
                assert symbol is not None
                normalized = dedupe_normalized_symbols([symbol])[0]
                revision = await self.add_desired([normalized])
                if await self._wait_for_target({*self.desired_symbols}, revision):
                    return self._record_control(
                        operation,
                        response_type,
                        {"success": None},
                    )
                return self._record_control(
                    operation,
                    response_type,
                    {
                        "failure": {
                            "symbol": normalized,
                            "reason": "TDX_SUBSCRIBE_NOT_CONVERGED",
                        }
                    },
                )

            if operation == "unsubscribe":
                assert symbol is not None
                normalized = dedupe_normalized_symbols([symbol])[0]
                revision = await self.remove_desired([normalized])
                target = set(self.desired_symbols)
                if await self._wait_for_target(target, revision):
                    return self._record_control(
                        operation,
                        response_type,
                        {"success": None},
                    )
                async with self._lock:
                    owner_fresh = self._is_owner_fresh()
                    still_active = normalized in self._last_reported_active
                if not owner_fresh:
                    return self._record_control(
                        operation,
                        response_type,
                        {
                            "failure": {
                                "symbol": normalized,
                                "reason": "TDX_UNSUBSCRIBE_VERIFY_FAILED",
                                "subscriptionState": "unknown",
                            }
                        },
                    )
                if still_active:
                    return self._record_control(
                        operation,
                        response_type,
                        {
                            "failure": {
                                "symbol": normalized,
                                "reason": "TDX_UNSUBSCRIBE_NOT_CONVERGED",
                                "subscriptionState": "subscribed",
                            }
                        },
                    )
                return self._record_control(
                    operation,
                    response_type,
                    {"success": None},
                )

            assert operation == "sync_subscriptions"
            target = dedupe_normalized_symbols(symbols or [])[: self.max_subscriptions]
            revision = await self.sync_desired(target)
            target_set = set(target)
            if await self._wait_for_target(target_set, revision):
                return self._record_control(
                    operation,
                    response_type,
                    {"success": None},
                )
            async with self._lock:
                owner_fresh = self._is_owner_fresh()
                observed = set(self._last_reported_active)
            if not owner_fresh:
                return self._record_control(
                    operation,
                    response_type,
                    {
                        "failure": {
                            "symbol": target[0] if target else "",
                            "reason": "TDX_UNSUBSCRIBE_VERIFY_FAILED",
                            "subscriptionState": "unknown",
                        }
                    },
                )
            extra = next(iter(sorted(observed - target_set)), None)
            if extra is not None:
                return self._record_control(
                    operation,
                    response_type,
                    {
                        "failure": {
                            "symbol": extra,
                            "reason": "TDX_UNSUBSCRIBE_NOT_CONVERGED",
                            "subscriptionState": "subscribed",
                        }
                    },
                )
            missing = next((item for item in target if item not in observed), "")
            return self._record_control(
                operation,
                response_type,
                {
                    "failure": {
                        "symbol": missing,
                        "reason": "TDX_SUBSCRIBE_NOT_CONVERGED",
                    }
                },
            )

    def _record_control(
        self,
        operation: str,
        response_type: str,
        data: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        result = "success" if "success" in data else "failure"
        reason = (
            "none"
            if result == "success"
            else str(cast(dict[str, Any], data["failure"]).get("reason", "unknown"))
        )
        key = (operation, result, reason)
        self._control_counts[key] = self._control_counts.get(key, 0) + 1
        return response_type, data

    async def _wait_for_target(self, target: set[str], revision: int) -> bool:
        deadline = time.monotonic() + self.control_timeout_seconds
        while True:
            async with self._lock:
                if (
                    self._desired_revision == revision
                    and self._converged_revision == revision
                    and self._observed_native_symbols == target
                ):
                    return True
                if self._desired_revision != revision:
                    return False
                self._convergence_changed.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(
                    self._convergence_changed.wait(),
                    timeout=remaining,
                )
            except TimeoutError:
                return False

    async def _wait_for_native_probe(self, probe_revision: int) -> bool:
        deadline = time.monotonic() + self.control_timeout_seconds
        while True:
            async with self._lock:
                if not self._is_owner_fresh():
                    return False
                if self._completed_native_probe_revision >= probe_revision:
                    return True
                self._convergence_changed.clear()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(
                    self._convergence_changed.wait(),
                    timeout=remaining,
                )
            except TimeoutError:
                return False

    # --- health --------------------------------------------------------

    def snapshot_age_seconds(self) -> float | None:
        """Age of the last accepted snapshot (None before first accept)."""
        if self._last_snapshot_monotonic is None:
            return None
        return round(time.monotonic() - self._last_snapshot_monotonic, 3)

    async def health(self) -> dict[str, Any]:
        async with self._lock:
            owner = self._owner
            ready = owner is not None and self._is_owner_fresh()
            return {
                "ready": ready,
                "ownerId": owner.owner_id if owner else None,
                "ownerGeneration": owner.generation if owner else 0,
                "ownerAgeSeconds": (
                    round(time.monotonic() - owner.last_seen_monotonic, 3) if owner else None
                ),
                "bridgeBuildId": owner.bridge_build_id if owner else None,
                "bridgeArtifactSha256": owner.bridge_artifact_sha256 if owner else None,
                "desiredRevision": self._desired_revision,
                "convergedRevision": self._converged_revision,
                "desiredSymbols": len(self._desired_symbols),
                "convergedSymbols": len(self._observed_native_symbols),
                "attemptedRevision": self._attempted_revision,
                "nativeProbeRevision": self._native_probe_revision,
                "completedNativeProbeRevision": self._completed_native_probe_revision,
                "reconcileRetryAttempt": self._reconcile_retry_attempt,
                "reconcileRetryAfterMs": self._remaining_retry_ms_locked(),
                "lastFailureCode": self._last_failure_code,
                "lastFailureRetryable": self._last_retryable,
                "lastSnapshotAt": self._last_snapshot_at,
                "lastSnapshotAgeSeconds": (
                    round(time.monotonic() - self._last_snapshot_monotonic, 3)
                    if self._last_snapshot_monotonic is not None
                    else None
                ),
                "pushState": self._stall.push_state,
                "stallDetected": self._stall.stall_detected,
                "stallEscalated": self._stall.stall_escalated,
                "controlTotals": [
                    {
                        "operation": operation,
                        "result": result,
                        "reason": reason,
                        "value": value,
                    }
                    for (operation, result, reason), value in sorted(
                        self._control_counts.items()
                    )
                ],
            }

    def _reset_reconcile_retry_locked(self) -> None:
        self._reconcile_retry_attempt = 0
        self._reconcile_retry_after_monotonic = None
        self._last_retryable = None
        self._last_failure_code = None

    def _remaining_retry_ms_locked(self) -> int:
        if self._reconcile_retry_after_monotonic is None:
            return 0
        return max(0, round((self._reconcile_retry_after_monotonic - time.monotonic()) * 1000))

    # --- helpers -------------------------------------------------------

    async def owner_matches(self, lease_token: str, stream_epoch: str) -> bool:
        """Return whether the pair identifies the active owner (non-raising).

        Used by auxiliary endpoints (e.g. observability) that must reject
        stray peers without consuming the snapshot pipeline.
        """
        async with self._lock:
            owner = self._owner
            return bool(
                owner is not None
                and secrets.compare_digest(owner.lease_token, lease_token)
                and secrets.compare_digest(owner.stream_epoch, stream_epoch)
            )

    def _require_owner_locked(self, lease_token: str) -> BridgeOwner:
        """Validate lease — MUST be called while holding self._lock.

        This prevents the concurrency window where lease is checked outside
        the lock, then a new owner registers (new epoch) before the lock is
        acquired, allowing a stale lease to write into the new epoch's state.
        """
        owner = self._owner
        if owner is None or not self._is_owner_fresh():
            raise GatewayError("TDX_BRIDGE_NO_OWNER", "no active bridge owner", retryable=True)
        if not secrets.compare_digest(owner.lease_token, lease_token):
            raise GatewayError("TDX_BRIDGE_LEASE_INVALID", "lease token mismatch", retryable=False)
        return owner

    def _require_owner_epoch_locked(self, lease_token: str, stream_epoch: str) -> BridgeOwner:
        """Validate the opaque lease and its generation fence under one lock."""
        owner = self._require_owner_locked(lease_token)
        if not secrets.compare_digest(owner.stream_epoch, stream_epoch):
            raise GatewayError(
                "TDX_BRIDGE_EPOCH_MISMATCH",
                "stream epoch does not match the active owner generation",
                retryable=False,
            )
        return owner

    def _is_owner_fresh(self) -> bool:
        if self._owner is None:
            return False
        age = time.monotonic() - self._owner.last_seen_monotonic
        return age <= OWNER_STALE_AFTER_SECONDS

    @property
    def owner(self) -> BridgeOwner | None:
        return self._owner if (self._owner and self._is_owner_fresh()) else None

    @property
    def desired_symbols(self) -> list[str]:
        return list(self._desired_symbols)

    @property
    def converged_revision(self) -> int:
        return self._converged_revision
