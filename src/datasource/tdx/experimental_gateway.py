"""Experimental TDX realtime gateway.

Control-plane authority for the experimental builtin-bridge pathway. Owns:
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

Data-plane snapshot validation lives in ``experimental_decoder``. This gateway
is transport/control only — it does not interpret price semantics.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from src.datasource.tdx.experimental_decoder import (
    decode_experimental_tdx_snapshot,
)
from src.datasource.tdx_normalization import dedupe_normalized_symbols

# Contract tuple accepted by this gateway build.
ACCEPTED_PAYLOAD_TYPE = "tdx.realtime.snapshot"
ACCEPTED_SCHEMA_VERSION = 0
ACCEPTED_DRAFT_REVISION = 1
ACCEPTED_ACQUISITION_PROFILE = "tdx.get_market_snapshot"

#: Owner stale after this many seconds without a poll/heartbeat.
OWNER_STALE_AFTER_SECONDS = 10.0
#: Subscription reconcile batch size.
RECONCILE_BATCH = 50


class GatewayError(Exception):
    """Base gateway error."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


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
    draft_revision: int
    last_seen_monotonic: float
    generation: int  # increments each owner registration


@dataclass
class _InstrumentState:
    """Per-instrument sequence fence (data plane, consumed by Mist via wire)."""

    last_outbound_sequence: int = 0
    last_producer_sequence: int = 0


@dataclass
class ExperimentalTdxRealtimeGateway:
    """Control-plane gateway for experimental TDX builtin bridge."""

    max_subscriptions: int = 100
    # Callback invoked when stream_epoch changes (owner generation change).
    # Set by the lifespan wiring to broadcast stream_started on the experimental
    # WS manager. Signature: async (stream_epoch: str) -> None.
    on_epoch_change: Any = None
    _owner: BridgeOwner | None = None
    _owner_generation_counter: int = 0
    # Desired subscription set (revisioned).
    _desired_symbols: list[str] = field(default_factory=lambda: list[str]())
    _desired_revision: int = 0
    # Four-state convergence.
    _attempted_revision: int = -1
    _converged_revision: int = -1
    _observed_native_symbols: set[str] = field(default_factory=lambda: set[str]())
    # Per-instrument outbound sequence fence.
    _sequences: dict[str, _InstrumentState] = field(
        default_factory=lambda: dict[str, _InstrumentState]()
    )
    # Accumulated accepted/rejected native symbols from the last result.
    _last_applied_active: list[str] = field(default_factory=lambda: list[str]())
    _last_rejected: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    # Async lock for state transitions.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    # --- owner / lease -------------------------------------------------

    async def register_owner(
        self,
        *,
        owner_id: str,
        bridge_build_id: str,
        bridge_artifact_sha256: str,
        acquisition_profile: str,
        schema_version: int,
        draft_revision: int,
    ) -> dict[str, Any]:
        """Register (or replace) the terminal owner. Returns lease info."""
        self._validate_contract_tuple(
            acquisition_profile=acquisition_profile,
            schema_version=schema_version,
            draft_revision=draft_revision,
        )
        async with self._lock:
            # Refuse to evict a fresh owner (must be stale or absent).
            if self._owner is not None and self._is_owner_fresh():
                existing = self._owner
                if existing.owner_id != owner_id:
                    raise GatewayError(
                        "TDX_BRIDGE_OWNER_ACTIVE",
                        f"another fresh owner {existing.owner_id!r} is active",
                        retryable=True,
                    )
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
                draft_revision=draft_revision,
                last_seen_monotonic=time.monotonic(),
                generation=generation,
            )
            # New generation resets convergence.
            self._attempted_revision = -1
            self._converged_revision = -1
            self._observed_native_symbols = set()
            self._sequences.clear()
            result = {
                "leaseToken": lease_token,
                "streamEpoch": stream_epoch,
                "acceptedContractTuple": {
                    "payloadType": ACCEPTED_PAYLOAD_TYPE,
                    "schemaVersion": ACCEPTED_SCHEMA_VERSION,
                    "draftRevision": ACCEPTED_DRAFT_REVISION,
                    "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
                },
            }
        # Broadcast stream_started to already-connected WS clients (outside lock).
        if self.on_epoch_change is not None:
            await self.on_epoch_change(stream_epoch)
        return result

    def _validate_contract_tuple(
        self, *, acquisition_profile: str, schema_version: int, draft_revision: int
    ) -> None:
        if (
            acquisition_profile != ACCEPTED_ACQUISITION_PROFILE
            or schema_version != ACCEPTED_SCHEMA_VERSION
            or draft_revision != ACCEPTED_DRAFT_REVISION
        ):
            raise GatewayError(
                "TDX_BRIDGE_CONTRACT_MISMATCH",
                f"contract tuple mismatch: got (acquisitionProfile={acquisition_profile},"
                f" schemaVersion={schema_version}, draftRevision={draft_revision})",
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
        """Set the desired subscription set (full replace). Returns new revision."""
        cleaned = dedupe_normalized_symbols(symbols)[: self.max_subscriptions]
        async with self._lock:
            if cleaned == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = cleaned
            self._desired_revision += 1
            return self._desired_revision

    async def add_desired(self, symbols: list[str]) -> int:
        cleaned = dedupe_normalized_symbols(symbols)
        async with self._lock:
            merged = dedupe_normalized_symbols([*self._desired_symbols, *cleaned])[
                : self.max_subscriptions
            ]
            if merged == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = merged
            self._desired_revision += 1
            return self._desired_revision

    async def remove_desired(self, symbols: list[str]) -> int:
        to_remove = set(dedupe_normalized_symbols(symbols))
        async with self._lock:
            merged = [s for s in self._desired_symbols if s not in to_remove]
            if merged == self._desired_symbols:
                return self._desired_revision
            self._desired_symbols = merged
            self._desired_revision += 1
            return self._desired_revision

    # --- poll / result ------------------------------------------------

    async def poll(
        self,
        *,
        lease_token: str,
        applied_revision: int = -1,  # noqa: ARG002
    ) -> dict[str, Any]:
        """Terminal polls for desired state."""
        owner = self._require_owner(lease_token)
        async with self._lock:
            owner.last_seen_monotonic = time.monotonic()
            return {
                "desiredRevision": self._desired_revision,
                "desiredSymbols": list(self._desired_symbols),
                "streamEpoch": owner.stream_epoch,
                # Reconcile instructions: unsubscribe extras first, then subscribe.
                "unsubscribe": [
                    s for s in self._observed_native_symbols if s not in self._desired_symbols
                ],
                "subscribe": [
                    s for s in self._desired_symbols if s not in self._observed_native_symbols
                ],
            }

    async def post_result(
        self,
        *,
        lease_token: str,
        desired_revision: int,
        applied_revision: int,
        active: list[str],
        rejected: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Terminal reports reconcile outcome (four-state convergence)."""
        owner = self._require_owner(lease_token)
        async with self._lock:
            owner.last_seen_monotonic = time.monotonic()
            # Stale revision gate: ignore results for revisions other than current desired.
            if desired_revision != self._desired_revision:
                return {"converged": False, "convergedRevision": self._converged_revision}
            self._attempted_revision = desired_revision
            self._last_applied_active = dedupe_normalized_symbols(active)
            self._last_rejected = rejected
            desired_set = set(self._desired_symbols)
            active_set = set(self._last_applied_active)
            # applied_revision must match desired_revision (sanity: terminal applied what it polled).
            converged = (
                applied_revision == desired_revision
                and len(rejected) == 0
                and active_set == desired_set
            )
            if converged:
                self._converged_revision = desired_revision
                self._observed_native_symbols = active_set
            else:
                # On non-convergence, clear observedNative so stale symbols
                # can no longer post snapshots until convergence is re-achieved.
                self._observed_native_symbols = set()
            return {
                "converged": converged,
                "convergedRevision": self._converged_revision,
            }

    # --- snapshot ingestion -------------------------------------------

    async def post_snapshot(
        self,
        *,
        lease_token: str,
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
        """
        owner = self._require_owner(lease_token)
        # Validate captured_at is RFC3339 (reject non-conforming timestamps).
        self._validate_rfc3339(captured_at, field_name="capturedAt")
        # Strict decode (raises ExperimentalDecoderError on bad data).
        snapshot = decode_experimental_tdx_snapshot(symbol, native, expected_code=symbol)
        # Converged-symbol gate: only accept symbols in the converged set.
        async with self._lock:
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
                snapshot=snapshot,
            )
            return {"accepted": True, "sequence": outbound_sequence, "frame": frame}

    @staticmethod
    def _validate_rfc3339(value: str, *, field_name: str) -> None:
        """Reject non-RFC3339 timestamps."""
        from src.datasource.contracts import normalize_beijing_iso

        try:
            result = normalize_beijing_iso(value)
        except (ValueError, TypeError):
            result = None
        if result is None:
            raise GatewayError(
                "TDX_BRIDGE_INVALID_TIMESTAMP",
                f"{field_name} is not a valid RFC3339 timestamp: {value!r}",
                retryable=False,
            )

    def _build_wire_frame(
        self,
        *,
        owner: BridgeOwner,
        symbol: str,
        sequence: int,
        captured_at: str,
        snapshot: Any,
    ) -> dict[str, Any]:
        return {
            "payloadType": ACCEPTED_PAYLOAD_TYPE,
            "schemaVersion": ACCEPTED_SCHEMA_VERSION,
            "draftRevision": ACCEPTED_DRAFT_REVISION,
            "contractStatus": "experimental",
            "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
            "streamEpoch": owner.stream_epoch,
            "sequence": sequence,
            "symbol": symbol,
            "capturedAt": captured_at,
            "eventTime": snapshot.eventTime,
            "snapshot": {
                "last": snapshot.last,
                "open": snapshot.open,
                "high": snapshot.high,
                "low": snapshot.low,
                "lastClose": snapshot.lastClose,
                "nativeVolume": snapshot.nativeVolume,
                "nativeAmount": snapshot.nativeAmount,
            },
            "unitStatus": "native-unverified",
            "quality": dict(snapshot.quality),
        }

    # --- health --------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        async with self._lock:
            owner = self._owner
            ready = owner is not None and self._is_owner_fresh()
            return {
                "tdxExperimentalBridgeReady": ready,
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
                "acceptedContractTuple": {
                    "payloadType": ACCEPTED_PAYLOAD_TYPE,
                    "schemaVersion": ACCEPTED_SCHEMA_VERSION,
                    "draftRevision": ACCEPTED_DRAFT_REVISION,
                    "acquisitionProfile": ACCEPTED_ACQUISITION_PROFILE,
                },
            }

    # --- helpers -------------------------------------------------------

    def _require_owner(self, lease_token: str) -> BridgeOwner:
        owner = self._owner
        if owner is None or not self._is_owner_fresh():
            raise GatewayError("TDX_BRIDGE_NO_OWNER", "no active bridge owner", retryable=True)
        if not secrets.compare_digest(owner.lease_token, lease_token):
            raise GatewayError("TDX_BRIDGE_LEASE_INVALID", "lease token mismatch", retryable=False)
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
