"""Formal TDX realtime gateway.

Control-plane authority for the builtin-bridge pathway. Owns:
- single-owner lease (with opaque token + stale eviction)
- four-state subscription convergence (desired / attempted / converged /
  observedNative) under a stable owner epoch
- authoritative outbound sequence reservation (before any await publish)
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
from typing import Any

from src.datasource.realtime_native_safety import validate_native_payload_safety
from src.datasource.tdx.realtime_native_validator import (
    validate_tdx_realtime_native_snapshot,
)
from src.datasource.tdx_normalization import dedupe_stable

# Contract tuple accepted by this gateway build.
ACCEPTED_PAYLOAD_TYPE = "mist.realtime.native_snapshot"
ACCEPTED_SCHEMA_VERSION = 1
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
class _InstrumentState:
    """Per-instrument sequence fence (data plane, consumed by Mist via wire)."""

    last_outbound_sequence: int = 0
    last_producer_sequence: int = 0


@dataclass
class TdxRealtimeGateway:
    """Control-plane gateway for the TDX builtin bridge."""

    max_subscriptions: int = 100
    # Callback invoked when stream_epoch changes (owner generation change).
    # Set by the lifespan wiring to broadcast stream_started on the realtime
    # WS manager. Signature: async (stream_epoch, generation, owner_id,
    # bridge_build_id) -> None.
    on_epoch_change: Any = None
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
    # Per-instrument outbound sequence fence.
    _sequences: dict[str, _InstrumentState] = field(
        default_factory=lambda: dict[str, _InstrumentState]()
    )
    # Accumulated accepted/rejected native symbols from the last result.
    _last_applied_active: list[str] = field(default_factory=lambda: list[str]())
    _last_rejected: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    _reconcile_retry_attempt: int = 0
    _reconcile_retry_after_monotonic: float | None = None
    _last_retryable: bool | None = None
    _last_failure_code: str | None = None
    _last_snapshot_monotonic: float | None = None
    _last_snapshot_at: str | None = None
    # Bounded loopback-only HIL evidence. One latest accepted native payload
    # per currently desired symbol; never contains the owner lease token.
    _native_evidence: dict[str, dict[str, Any]] = field(
        default_factory=lambda: dict[str, dict[str, Any]]()
    )
    # Async lock for state transitions.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # Separate lock to serialize epoch-change broadcasts (prevents out-of-order
    # broadcast when concurrent same-owner registrations interleave).
    _broadcast_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

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
            self._owner_generation_counter += 1
            generation = self._owner_generation_counter
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
            self._reset_reconcile_retry_locked()
            self._sequences.clear()
            self._native_evidence.clear()
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
        # Broadcast stream_started, serialized by _broadcast_lock to guarantee
        # in-generation-order delivery. Also re-check generation after acquiring
        # broadcast lock to skip stale broadcasts.
        if self.on_epoch_change is not None:
            async with self._broadcast_lock:
                current: Any = self._owner
                if current is not None and current.generation == generation:
                    await self.on_epoch_change(
                        stream_epoch,
                        generation,
                        current.owner_id,
                        current.bridge_build_id,
                    )
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
        cleaned = dedupe_stable(symbols)[: self.max_subscriptions]
        async with self._lock:
            if cleaned == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = cleaned
            self._desired_revision += 1
            # Invalidate convergence: old observedNative is stale for the new revision.
            # Do NOT clear _sequences — outbound sequence must be monotonic per
            # epoch, not per revision. Clearing it would reset sequence to 0 and
            # cause Mist to reject the next frame as duplicate/out-of-order.
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._native_evidence.clear()
            self._reset_reconcile_retry_locked()
            return self._desired_revision

    async def add_desired(self, symbols: list[str]) -> int:
        cleaned = dedupe_stable(symbols)
        async with self._lock:
            merged = dedupe_stable([*self._desired_symbols, *cleaned])[: self.max_subscriptions]
            if merged == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = merged
            self._desired_revision += 1
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._native_evidence.clear()
            self._reset_reconcile_retry_locked()
            return self._desired_revision

    async def remove_desired(self, symbols: list[str]) -> int:
        to_remove = set(dedupe_stable(symbols))
        async with self._lock:
            merged = [s for s in self._desired_symbols if s not in to_remove]
            if merged == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = merged
            self._desired_revision += 1
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._native_evidence.clear()
            self._reset_reconcile_retry_locked()
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
                # Reconcile instructions based on _last_reported_active (what the
                # terminal actually has), NOT _observed_native_symbols (converged set
                # which is cleared on desired change). This ensures unsubscribe is
                # correctly computed even after desired shrinks.
                "unsubscribe": [
                    s for s in self._last_reported_active if s not in self._desired_symbols
                ],
                "subscribe": [
                    s for s in self._desired_symbols if s not in self._last_reported_active
                ],
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
            self._last_applied_active = dedupe_stable(active)
            self._last_reported_active = set(self._last_applied_active)
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
        producer_sequence: int,
        captured_at: str,
        native: dict[str, Any],
    ) -> dict[str, Any]:
        """Terminal posts a native snapshot. Gateway validates, decodes, assigns
        authoritative outbound sequence, and returns the typed frame.

        producer_sequence is used for HTTP-retry idempotency: a duplicate
        (same producer_sequence for same symbol+epoch) is dropped, not re-broadcast.
        Sequence reservation happens synchronously before any await publish.
        Lease/epoch validation is inside the lock to prevent cross-generation
        concurrent penetration.
        """
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
            state = self._sequences.setdefault(symbol, _InstrumentState())
            # Idempotency: reject duplicate producer_sequence (HTTP retry).
            if producer_sequence <= state.last_producer_sequence:
                raise GatewayError(
                    "TDX_BRIDGE_DUPLICATE_PRODUCER_SEQUENCE",
                    f"duplicate producer_sequence={producer_sequence} for {symbol}"
                    f" (last={state.last_producer_sequence})",
                    retryable=False,
                )
            state.last_producer_sequence = producer_sequence
            # Authoritative outbound sequence (monotonic per instrument+epoch).
            outbound_sequence = state.last_outbound_sequence + 1
            state.last_outbound_sequence = outbound_sequence
            frame = self._build_wire_frame(
                owner=owner,
                symbol=symbol,
                sequence=outbound_sequence,
                captured_at=captured_at,
                native=native,
            )
            self._last_snapshot_monotonic = time.monotonic()
            self._last_snapshot_at = dt.datetime.now(dt.UTC).isoformat()
            self._native_evidence[symbol] = {
                "symbol": symbol,
                "ownerId": owner.owner_id,
                "bridgeBuildId": owner.bridge_build_id,
                "generation": owner.generation,
                "streamEpoch": owner.stream_epoch,
                "producerSequence": producer_sequence,
                "capturedAt": captured_at,
                "native": copy.deepcopy(native),
                "frame": copy.deepcopy(frame),
            }
            return {"accepted": True, "sequence": outbound_sequence, "frame": frame}

    async def read_native_evidence(self, symbol: str) -> dict[str, Any]:
        """Return the latest accepted native HIL evidence for one symbol.

        The route layer keeps this loopback-only. Returning a deep copy avoids
        callers mutating gateway state, and the stored shape deliberately has
        no lease token.
        """
        async with self._lock:
            evidence = self._native_evidence.get(symbol)
            if evidence is None or symbol not in self._desired_symbols:
                raise GatewayError(
                    "TDX_BRIDGE_EVIDENCE_NOT_FOUND",
                    f"no native evidence for {symbol}",
                    retryable=True,
                )
            return copy.deepcopy(evidence)

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
        owner: BridgeOwner,
        symbol: str,
        sequence: int,
        captured_at: str,
        native: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "payloadType": ACCEPTED_PAYLOAD_TYPE,
            "schemaVersion": ACCEPTED_SCHEMA_VERSION,
            "source": "tdx",
            "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
            "streamEpoch": owner.stream_epoch,
            "sequence": sequence,
            "sequenceScope": "symbol",
            "symbol": symbol,
            "capturedAt": captured_at,
            "native": copy.deepcopy(native),
        }

    # --- health --------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        async with self._lock:
            owner = self._owner
            ready = owner is not None and self._is_owner_fresh()
            return {
                "tdxRealtimeBridgeReady": ready,
                "ownerId": owner.owner_id if owner else None,
                "ownerAgeSeconds": (
                    round(time.monotonic() - owner.last_seen_monotonic, 3) if owner else None
                ),
                "bridgeBuildId": owner.bridge_build_id if owner else None,
                "streamEpoch": owner.stream_epoch if owner else None,
                "desiredRevision": self._desired_revision,
                "convergedRevision": self._converged_revision,
                "desiredSymbols": len(self._desired_symbols),
                "convergedSymbols": len(self._observed_native_symbols),
                "attemptedRevision": self._attempted_revision,
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
                "acceptedContractTuple": {
                    "payloadType": ACCEPTED_PAYLOAD_TYPE,
                    "schemaVersion": ACCEPTED_SCHEMA_VERSION,
                    "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
                },
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
