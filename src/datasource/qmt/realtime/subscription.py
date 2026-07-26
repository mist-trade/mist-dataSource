"""QMT native subscription control, registry, and durable journal."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import os
import re
import secrets
import threading
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from src.datasource.qmt.realtime.contract import QMT_SYMBOL_PATTERN
from src.datasource.realtime_native_safety import (
    NativePayloadSafetyError,
    validate_native_payload_safety,
)

DEFAULT_JOURNAL_PATH = r"F:\quant\MistAPI\datasource\state\qmt\subscription-journal.jsonl"
DEFAULT_JOURNAL_ROTATE_BYTES = 67_108_864
DEFAULT_JOURNAL_ARCHIVE_MAX_BYTES = 536_870_912
DEFAULT_JOURNAL_RESOLVED_RETENTION_DAYS = 90
MAX_JOURNAL_RECORD_BYTES = 65_536
MIN_ROTATION_OVERHEAD_BYTES = MAX_JOURNAL_RECORD_BYTES * 2
DEFAULT_CONTROL_TIMEOUT_SECONDS = 10.0
QMT_UNSUBSCRIBE_SUCCESS_VALUES_ENV = "MIST_QMT_UNSUBSCRIBE_SUCCESS_VALUES"
RFC3339_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d"
    r"(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)

SubscriptionState = Literal["subscribed", "unknown"]
ControlResponseType = Literal[
    "subscriptions_synced",
    "subscribed",
    "unsubscribed",
    "subscriptions",
]
NativeMethod = Literal[
    "subscribe_quote",
    "subscribe_whole_quote",
    "unsubscribe_quote",
]


class QmtSubscriptionControlError(Exception):
    """Stable failure raised by the datasource subscription controller."""

    def __init__(
        self,
        reason: str,
        *,
        symbol: str | None = None,
        subscription_state: SubscriptionState | None = None,
    ) -> None:
        super().__init__(reason)
        self.reason: str = reason
        self.symbol: str | None = symbol
        self.subscription_state: SubscriptionState | None = subscription_state


class QmtSubscriptionSequenceError(Exception):
    """Raised when a native result does not belong to the current slot."""


class QmtSubscriptionJournalError(Exception):
    """Raised when subscription evidence cannot be made durable."""


@dataclass(frozen=True)
class QmtWholeSubscription:
    sub_id: int
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class QmtNativeReply:
    success_present: bool
    success: Any | None
    failure: dict[str, Any] | None


@dataclass
class _NativeSlot:
    call_sequence: int
    method: NativeMethod
    command: dict[str, Any]
    future: asyncio.Future[QmtNativeReply]
    created_at: float
    exposed: bool = False


class QmtSubscriptionRegistry:
    """Authoritative process-local QMT whole/single handle registry."""

    def __init__(self) -> None:
        self.whole: QmtWholeSubscription | None = None
        self.singles: dict[str, int] = {}
        self.retained_recovery: set[tuple[str, str | None, int]] = set()

    def public_value(self) -> dict[str, Any]:
        whole: dict[str, Any] | None = None
        if self.whole is not None:
            whole = {
                "subId": self.whole.sub_id,
                "symbols": list(self.whole.symbols),
            }
        return {
            "whole": whole,
            "singles": dict(sorted(self.singles.items())),
        }

    def owns(self, subscription_id: int, symbol: str) -> bool:
        if self.whole is not None and self.whole.sub_id == subscription_id:
            return symbol in self.whole.symbols
        return self.singles.get(symbol) == subscription_id

    def contains_symbol(self, symbol: str) -> bool:
        return self.whole is not None and symbol in self.whole.symbols or symbol in self.singles


class QmtSubscriptionJournal:
    """Single-writer append-only JSONL journal with bounded rotation."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        rotate_bytes: int | str | None = None,
        archive_max_bytes: int | str | None = None,
        resolved_retention_days: int | str | None = None,
    ) -> None:
        self.path = Path(
            path or os.environ.get("MIST_QMT_SUBSCRIPTION_JOURNAL_PATH") or DEFAULT_JOURNAL_PATH
        )
        self.rotate_bytes = _positive_int(
            rotate_bytes
            if rotate_bytes is not None
            else os.environ.get(
                "MIST_QMT_SUBSCRIPTION_JOURNAL_ROTATE_BYTES",
                DEFAULT_JOURNAL_ROTATE_BYTES,
            ),
            "MIST_QMT_SUBSCRIPTION_JOURNAL_ROTATE_BYTES",
        )
        self.archive_max_bytes = _positive_int(
            archive_max_bytes
            if archive_max_bytes is not None
            else os.environ.get(
                "MIST_QMT_SUBSCRIPTION_JOURNAL_ARCHIVE_MAX_BYTES",
                DEFAULT_JOURNAL_ARCHIVE_MAX_BYTES,
            ),
            "MIST_QMT_SUBSCRIPTION_JOURNAL_ARCHIVE_MAX_BYTES",
        )
        self.resolved_retention_days = _positive_int(
            resolved_retention_days
            if resolved_retention_days is not None
            else os.environ.get(
                "MIST_QMT_SUBSCRIPTION_JOURNAL_RESOLVED_RETENTION_DAYS",
                DEFAULT_JOURNAL_RESOLVED_RETENTION_DAYS,
            ),
            "MIST_QMT_SUBSCRIPTION_JOURNAL_RESOLVED_RETENTION_DAYS",
        )
        if self.rotate_bytes < MIN_ROTATION_OVERHEAD_BYTES:
            raise ValueError(
                "MIST_QMT_SUBSCRIPTION_JOURNAL_ROTATE_BYTES cannot hold "
                "a bounded record and rotation anchor"
            )
        if self.archive_max_bytes < self.rotate_bytes * 2:
            raise ValueError(
                "MIST_QMT_SUBSCRIPTION_JOURNAL_ARCHIVE_MAX_BYTES must be "
                "at least twice the rotate threshold"
            )
        self._lock = threading.Lock()
        self._record_sequence = 0
        self._previous_hash = "0" * 64
        self._archive_index = 0
        self.healthy = True
        self.last_error: str | None = None
        self.last_rotation_at: str | None = None
        self._recover_interrupted_rotation()
        self._load_tail()

    def append(self, kind: str, detail: Mapping[str, Any]) -> dict[str, Any]:
        with self._lock:
            try:
                record = self._build_record(kind, detail)
                encoded = _encode_record(record)
                if len(encoded) > MAX_JOURNAL_RECORD_BYTES:
                    raise QmtSubscriptionJournalError(
                        "QMT subscription journal record exceeds bounded size"
                    )
                sequence_before_capacity = self._record_sequence
                self._ensure_capacity(len(encoded))
                if self._record_sequence != sequence_before_capacity:
                    record = self._build_record(kind, detail)
                    encoded = _encode_record(record)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._record_sequence = cast(int, record["sequence"])
                self._previous_hash = cast(str, record["hash"])
                self.healthy = True
                self.last_error = None
                return record
            except Exception as exc:
                self.healthy = False
                self.last_error = type(exc).__name__ + ": " + str(exc)
                if isinstance(exc, QmtSubscriptionJournalError):
                    raise
                raise QmtSubscriptionJournalError(self.last_error) from exc

    def _build_record(self, kind: str, detail: Mapping[str, Any]) -> dict[str, Any]:
        body = {
            "sequence": self._record_sequence + 1,
            "recordedAt": datetime.now(UTC).isoformat(),
            "kind": kind,
            "detail": _journal_safe(detail),
            "previousHash": self._previous_hash,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**body, "hash": digest}

    def _ensure_capacity(self, next_bytes: int) -> None:
        active_bytes = self.path.stat().st_size if self.path.exists() else 0
        total_bytes = sum(
            item.stat().st_size
            for item in self.path.parent.glob(self.path.name + "*")
            if item.is_file()
        )
        if total_bytes + next_bytes > self.archive_max_bytes:
            raise QmtSubscriptionJournalError(
                "QMT subscription journal pinned evidence reached the byte limit"
            )
        if active_bytes and active_bytes + next_bytes > self.rotate_bytes:
            self._rotate()

    def _rotate(self) -> None:
        rotating = self.path.with_name(self.path.name + ".rotating")
        if rotating.exists():
            raise QmtSubscriptionJournalError(
                "QMT subscription journal has unresolved rotating state"
            )
        os.replace(self.path, rotating)
        archive_name = (
            self.path.name
            + "."
            + str(self._record_sequence)
            + "."
            + str(self._archive_index + 1)
            + ".jsonl"
        )
        archive = self.path.with_name(archive_name)
        os.replace(rotating, archive)
        archive_digest = _sha256_file(archive)
        _atomic_text_write(
            archive.with_suffix(archive.suffix + ".sha256"),
            archive_digest + "  " + archive.name + "\n",
        )
        manifest = {
            "archive": archive.name,
            "sha256": archive_digest,
            "lastRecordSequence": self._record_sequence,
            "previousHash": self._previous_hash,
        }
        _atomic_json_write(self.path.with_name(self.path.name + ".manifest.json"), manifest)
        self._archive_index += 1
        anchor = self._build_record(
            "rotation_anchor",
            {
                "archive": archive.name,
                "archiveSha256": archive_digest,
                "lastRecordSequence": self._record_sequence,
            },
        )
        encoded = _encode_record(anchor)
        with self.path.open("wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        self._record_sequence = cast(int, anchor["sequence"])
        self._previous_hash = cast(str, anchor["hash"])
        self.last_rotation_at = datetime.now(UTC).isoformat()

    def _recover_interrupted_rotation(self) -> None:
        rotating = self.path.with_name(self.path.name + ".rotating")
        temporary = self.path.with_name(self.path.name + ".tmp")
        if temporary.exists():
            temporary.unlink()
        if rotating.exists():
            if self.path.exists():
                raise QmtSubscriptionJournalError(
                    "ambiguous QMT subscription journal rotation state"
                )
            os.replace(rotating, self.path)

    def _load_tail(self) -> None:
        archives = sorted(
            self.path.parent.glob(self.path.name + ".*.*.jsonl"),
            key=_archive_sort_key,
        )
        paths = [*archives]
        if self.path.exists():
            paths.append(self.path)
        if not paths:
            return
        try:
            expected_sequence = 1
            previous_hash = "0" * 64
            for path in paths:
                sidecar = path.with_suffix(path.suffix + ".sha256")
                if path != self.path and sidecar.exists():
                    expected_digest = sidecar.read_text(encoding="utf-8").split()[0]
                    if _sha256_file(path) != expected_digest:
                        raise QmtSubscriptionJournalError(
                            "QMT subscription journal archive checksum mismatch"
                        )
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        if not line.strip():
                            continue
                        record = cast(dict[str, Any], json.loads(line))
                        digest = str(record.get("hash", ""))
                        body = {key: value for key, value in record.items() if key != "hash"}
                        calculated = hashlib.sha256(
                            json.dumps(
                                body,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest()
                        if (
                            int(record.get("sequence", -1)) != expected_sequence
                            or record.get("previousHash") != previous_hash
                            or not secrets.compare_digest(digest, calculated)
                        ):
                            raise QmtSubscriptionJournalError(
                                "QMT subscription journal hash chain mismatch"
                            )
                        expected_sequence += 1
                        previous_hash = digest
            self._record_sequence = expected_sequence - 1
            self._previous_hash = previous_hash
        except Exception as exc:
            self.healthy = False
            self.last_error = type(exc).__name__ + ": " + str(exc)
            raise QmtSubscriptionJournalError(self.last_error) from exc

    def health(self) -> dict[str, Any]:
        archive_paths = list(self.path.parent.glob(self.path.name + ".*.*.jsonl"))
        return {
            "activeBytes": self.path.stat().st_size if self.path.exists() else 0,
            "archiveBytes": sum(item.stat().st_size for item in archive_paths),
            "rotateBytes": self.rotate_bytes,
            "archiveMaxBytes": self.archive_max_bytes,
            "resolvedRetentionDays": self.resolved_retention_days,
            "lastRotationAt": self.last_rotation_at,
        }

    @property
    def record_sequence(self) -> int:
        return self._record_sequence


class QmtSubscriptionController:
    """Execute explicit backend control through one loopback native-call slot."""

    def __init__(
        self,
        *,
        journal: QmtSubscriptionJournal,
        owner_validator: Callable[[str, str, int], None],
        publisher: Callable[[dict[str, Any]], Awaitable[None] | None],
        unsubscribe_success_values: frozenset[int] = frozenset(),
        timeout_seconds: float = DEFAULT_CONTROL_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = QmtSubscriptionRegistry()
        self.journal = journal
        self._owner_validator = owner_validator
        self._publisher = publisher
        self._unsubscribe_success_values = unsubscribe_success_values
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._mutation_lock = asyncio.Lock()
        self._slot: _NativeSlot | None = None
        self._call_sequence = 0
        self.reconciliation_required = self.journal.record_sequence > 0
        self._control_counts: dict[tuple[str, str, str], int] = {}

    async def execute(
        self,
        request_type: str,
        *,
        symbol: str | None = None,
        symbols: Sequence[str] | None = None,
    ) -> tuple[ControlResponseType, dict[str, Any]]:
        response_type = _response_type(request_type)
        if request_type == "get_subscriptions":
            return self._record_control(
                request_type,
                response_type,
                {"success": self.registry.public_value()},
            )
        if self._mutation_lock.locked():
            return self._record_control(
                request_type,
                response_type,
                _generic_failure(symbol, "QMT_SUBSCRIPTION_CONTROL_BUSY"),
            )
        async with self._mutation_lock:
            if self.reconciliation_required or not self.journal.healthy:
                return self._record_control(
                    request_type,
                    response_type,
                    _generic_failure(symbol, "QMT_JOURNAL_RECONCILIATION_REQUIRED"),
                )
            try:
                if request_type == "sync_subscriptions":
                    value = await self._sync(symbols or ())
                elif request_type == "subscribe":
                    value = await self._subscribe(_normalize_symbol(symbol))
                elif request_type == "unsubscribe":
                    value = await self._unsubscribe(_normalize_symbol(symbol))
                else:
                    raise QmtSubscriptionControlError(
                        "QMT_SUBSCRIPTION_OPERATION_UNSUPPORTED", symbol=symbol
                    )
                return self._record_control(
                    request_type,
                    response_type,
                    {"success": value},
                )
            except QmtSubscriptionControlError as exc:
                if exc.subscription_state is None:
                    data = _generic_failure(exc.symbol, exc.reason)
                else:
                    data = _state_failure(
                        exc.symbol,
                        exc.reason,
                        exc.subscription_state,
                    )
                return self._record_control(request_type, response_type, data)

    def poll_command(
        self, owner_id: str, lease_token: str, generation: int
    ) -> dict[str, Any] | None:
        self._owner_validator(owner_id, lease_token, generation)
        slot = self._slot
        if slot is None or slot.exposed:
            return None
        slot.exposed = True
        return dict(slot.command)

    def post_result(
        self,
        owner_id: str,
        lease_token: str,
        generation: int,
        call_sequence: int,
        reply: QmtNativeReply,
    ) -> None:
        self._owner_validator(owner_id, lease_token, generation)
        if type(call_sequence) is not int or call_sequence <= 0:
            raise QmtSubscriptionSequenceError("QMT callSequence must be an exact positive integer")
        slot = self._slot
        if slot is None or not slot.exposed or slot.call_sequence != call_sequence:
            raise QmtSubscriptionSequenceError(
                "QMT subscription result does not match the current callSequence"
            )
        if slot.future.done():
            raise QmtSubscriptionSequenceError("QMT subscription result slot is already closed")
        slot.future.set_result(reply)

    async def accept_snapshot(
        self,
        owner_id: str,
        lease_token: str,
        generation: int,
        subscription_id: int,
        captured_at: str,
        native: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._owner_validator(owner_id, lease_token, generation)
        if not RFC3339_PATTERN.fullmatch(captured_at):
            raise QmtSubscriptionControlError("QMT_SNAPSHOT_CAPTURED_AT_INVALID")
        try:
            datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QmtSubscriptionControlError(
                "QMT_SNAPSHOT_CAPTURED_AT_INVALID"
            ) from exc
        if type(subscription_id) is not int:
            raise QmtSubscriptionControlError("QMT_SNAPSHOT_SUBSCRIPTION_ID_INVALID")
        accepted: dict[str, Any] = {}
        rejected: list[dict[str, str]] = []
        for raw_symbol, value in native.items():
            symbol = str(raw_symbol).strip().upper()
            if not QMT_SYMBOL_PATTERN.fullmatch(symbol):
                rejected.append({"symbol": symbol, "reason": "QMT_SNAPSHOT_SYMBOL_INVALID"})
                continue
            if not self.registry.owns(subscription_id, symbol):
                rejected.append({"symbol": symbol, "reason": "QMT_SNAPSHOT_NON_MEMBER"})
                continue
            if not isinstance(value, dict):
                rejected.append({"symbol": symbol, "reason": "QMT_SNAPSHOT_NATIVE_INVALID"})
                continue
            try:
                validate_native_payload_safety(cast(dict[str, Any], value))
            except NativePayloadSafetyError:
                rejected.append({"symbol": symbol, "reason": "QMT_SNAPSHOT_NATIVE_UNSAFE"})
                continue
            accepted[symbol] = value
        if accepted:
            published = self._publisher(
                {
                    "schemaVersion": 2,
                    "capturedAt": captured_at,
                    "native": accepted,
                }
            )
            if inspect.isawaitable(published):
                await published
        return {"accepted": sorted(accepted), "rejected": rejected}

    def health(self) -> dict[str, Any]:
        return {
            "ready": self.journal.healthy and not self.reconciliation_required,
            "journalHealthy": self.journal.healthy,
            "journalError": self.journal.last_error,
            "reconciliationRequired": self.reconciliation_required,
            "retainedRecoveryCount": len(self.registry.retained_recovery),
            "wholeHandleCount": 1 if self.registry.whole is not None else 0,
            "singleHandleCount": len(self.registry.singles),
            "inFlight": self._slot is not None,
            "callSequence": self._call_sequence,
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
            "journal": self.journal.health(),
        }

    def observe_rebuilt_context(self) -> None:
        """Unlock a restarted datasource only after operator-proven context rebuild."""
        self.journal.append(
            "operator_observation",
            {
                "observation": "qmt_context_rebuilt",
                "physicalSubscriptionsAssumedReleased": True,
            },
        )
        self.registry = QmtSubscriptionRegistry()
        self.reconciliation_required = False

    def _record_control(
        self,
        operation: str,
        response_type: ControlResponseType,
        data: dict[str, Any],
    ) -> tuple[ControlResponseType, dict[str, Any]]:
        result = "success" if "success" in data else "failure"
        reason = (
            "none"
            if result == "success"
            else str(cast(dict[str, Any], data["failure"]).get("reason", "unknown"))
        )
        key = (operation, result, reason)
        self._control_counts[key] = self._control_counts.get(key, 0) + 1
        return response_type, data

    async def _sync(self, symbols: Sequence[str]) -> int | None:
        desired = _normalize_symbols(symbols)
        failures: list[QmtSubscriptionControlError] = []
        whole = self.registry.whole
        if whole is not None:
            failure = await self._cancel_handle(
                bucket="whole",
                symbol=None,
                sub_id=whole.sub_id,
            )
            if failure is not None:
                failures.append(failure)
                if self.reconciliation_required:
                    raise failure
        for symbol in sorted(self.registry.singles):
            sub_id = self.registry.singles[symbol]
            failure = await self._cancel_handle(
                bucket="single",
                symbol=symbol,
                sub_id=sub_id,
            )
            if failure is not None:
                failures.append(failure)
                if self.reconciliation_required:
                    raise failure
        if failures:
            raise failures[0]
        if not desired:
            return None
        return await self._subscribe_whole(desired)

    async def _subscribe(self, symbol: str) -> int:
        if self.registry.contains_symbol(symbol):
            raise QmtSubscriptionControlError(
                "QMT_SUBSCRIPTION_DUPLICATE",
                symbol=symbol,
            )
        reply, durable = await self._native_call(
            "subscribe_quote",
            {"symbol": symbol},
        )
        sub_id = _exact_subscription_id(reply, symbol)
        self.registry.singles[symbol] = sub_id
        if not durable or not self._append_transition(
            "single_subscribed", {"symbol": symbol, "subId": sub_id}
        ):
            self._retain_after_durability_failure("single", symbol, sub_id)
            raise QmtSubscriptionControlError("QMT_JOURNAL_DURABILITY_FAILED", symbol=symbol)
        return sub_id

    async def _subscribe_whole(self, symbols: tuple[str, ...]) -> int:
        reply, durable = await self._native_call(
            "subscribe_whole_quote",
            {"symbols": list(symbols)},
        )
        sub_id = _exact_subscription_id(reply, None)
        self.registry.whole = QmtWholeSubscription(sub_id=sub_id, symbols=symbols)
        if not durable or not self._append_transition(
            "whole_subscribed", {"symbols": list(symbols), "subId": sub_id}
        ):
            self._retain_after_durability_failure("whole", None, sub_id)
            raise QmtSubscriptionControlError("QMT_JOURNAL_DURABILITY_FAILED")
        return sub_id

    async def _unsubscribe(self, symbol: str) -> None:
        if self.registry.whole is not None and symbol in self.registry.whole.symbols:
            raise QmtSubscriptionControlError(
                "QMT_SYMBOL_OWNED_BY_WHOLE",
                symbol=symbol,
                subscription_state="subscribed",
            )
        sub_id = self.registry.singles.get(symbol)
        if sub_id is None:
            raise QmtSubscriptionControlError(
                "QMT_SUBSCRIPTION_NOT_FOUND",
                symbol=symbol,
                subscription_state="unknown",
            )
        failure = await self._cancel_handle(
            bucket="single",
            symbol=symbol,
            sub_id=sub_id,
        )
        if failure is not None:
            raise failure
        return None

    async def _cancel_handle(
        self,
        *,
        bucket: Literal["whole", "single"],
        symbol: str | None,
        sub_id: int,
    ) -> QmtSubscriptionControlError | None:
        try:
            reply, durable = await self._native_call(
                "unsubscribe_quote",
                {"subId": sub_id, "symbol": symbol},
            )
        except QmtSubscriptionControlError as exc:
            return QmtSubscriptionControlError(
                exc.reason,
                symbol=symbol,
                subscription_state="unknown",
            )
        if (
            not reply.success_present
            or type(reply.success) is not int
            or reply.success not in self._unsubscribe_success_values
        ):
            return QmtSubscriptionControlError(
                "QMT_UNSUBSCRIBE_UNCONFIRMED",
                symbol=symbol,
                subscription_state="unknown",
            )
        if not durable or not self._append_transition(
            "unsubscribed",
            {"bucket": bucket, "symbol": symbol, "subId": sub_id},
        ):
            self._retain_after_durability_failure(bucket, symbol, sub_id)
            return QmtSubscriptionControlError(
                "QMT_JOURNAL_DURABILITY_FAILED",
                symbol=symbol,
                subscription_state="unknown",
            )
        if bucket == "whole":
            self.registry.whole = None
        elif symbol is not None:
            self.registry.singles.pop(symbol, None)
        return None

    async def _native_call(
        self,
        method: NativeMethod,
        fields: dict[str, Any],
    ) -> tuple[QmtNativeReply, bool]:
        if self._slot is not None:
            raise QmtSubscriptionControlError("QMT_SUBSCRIPTION_CONTROL_BUSY")
        call_sequence = self._call_sequence + 1
        command = {"callSequence": call_sequence, "method": method, **fields}
        try:
            self.journal.append(
                "native_intent",
                {"callSequence": call_sequence, "method": method, **fields},
            )
        except QmtSubscriptionJournalError as exc:
            raise QmtSubscriptionControlError("QMT_JOURNAL_DURABILITY_FAILED") from exc
        self._call_sequence = call_sequence
        loop = asyncio.get_running_loop()
        slot = _NativeSlot(
            call_sequence=call_sequence,
            method=method,
            command=command,
            future=loop.create_future(),
            created_at=self._clock(),
        )
        self._slot = slot
        try:
            try:
                reply = await asyncio.wait_for(slot.future, timeout=self._timeout_seconds)
            except TimeoutError as exc:
                raise QmtSubscriptionControlError("QMT_SUBSCRIPTION_CALL_TIMEOUT") from exc
            durable = True
            try:
                self.journal.append(
                    "native_result",
                    {
                        "callSequence": call_sequence,
                        "method": method,
                        "successPresent": reply.success_present,
                        "success": reply.success,
                        "failure": reply.failure,
                    },
                )
            except QmtSubscriptionJournalError:
                durable = False
            if reply.failure is not None:
                raise QmtSubscriptionControlError(
                    reply.failure["reason"],
                    symbol=reply.failure.get("symbol"),
                )
            return reply, durable
        finally:
            if self._slot is slot:
                self._slot = None

    def _append_transition(self, kind: str, detail: Mapping[str, Any]) -> bool:
        try:
            self.journal.append("registry_transition", {"transition": kind, **detail})
            return True
        except QmtSubscriptionJournalError:
            return False

    def _retain_after_durability_failure(
        self,
        bucket: str,
        symbol: str | None,
        sub_id: int,
    ) -> None:
        self.registry.retained_recovery.add((bucket, symbol, sub_id))
        self.reconciliation_required = True


def _response_type(request_type: str) -> ControlResponseType:
    mapping: dict[str, ControlResponseType] = {
        "sync_subscriptions": "subscriptions_synced",
        "subscribe": "subscribed",
        "unsubscribe": "unsubscribed",
        "get_subscriptions": "subscriptions",
    }
    try:
        return mapping[request_type]
    except KeyError as exc:
        raise QmtSubscriptionControlError("QMT_SUBSCRIPTION_OPERATION_UNSUPPORTED") from exc


def _normalize_symbol(value: str | None) -> str:
    symbol = str(value or "").strip().upper()
    if not QMT_SYMBOL_PATTERN.fullmatch(symbol):
        raise QmtSubscriptionControlError("QMT_SUBSCRIPTION_SYMBOL_INVALID", symbol=symbol)
    return symbol


def _normalize_symbols(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted({_normalize_symbol(value) for value in values}))


def _exact_subscription_id(reply: QmtNativeReply, symbol: str | None) -> int:
    if reply.failure is not None or not reply.success_present or type(reply.success) is not int:
        raise QmtSubscriptionControlError(
            "QMT_INVALID_SUBSCRIPTION_ID",
            symbol=symbol,
        )
    return reply.success


def _generic_failure(symbol: str | None, reason: str) -> dict[str, Any]:
    return {"failure": {"symbol": symbol, "reason": reason}}


def _state_failure(
    symbol: str | None,
    reason: str,
    subscription_state: SubscriptionState,
) -> dict[str, Any]:
    return {
        "failure": {
            "symbol": symbol,
            "reason": reason,
            "subscriptionState": subscription_state,
        }
    }


def _positive_int(value: int | str, name: str) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ValueError(name + " must be an exact positive integer")
    if parsed <= 0:
        raise ValueError(name + " must be an exact positive integer")
    return parsed


def configured_qmt_unsubscribe_success_values() -> frozenset[int]:
    raw = os.environ.get(QMT_UNSUBSCRIBE_SUCCESS_VALUES_ENV, "").strip()
    if not raw:
        return frozenset()
    values: set[int] = set()
    for item in raw.split(","):
        value = item.strip()
        if not value or value in {"+", "-"}:
            raise ValueError(
                QMT_UNSUBSCRIBE_SUCCESS_VALUES_ENV
                + " must be a comma-separated exact integer set"
            )
        unsigned = value[1:] if value[0] in {"+", "-"} else value
        if not unsigned.isdigit():
            raise ValueError(
                QMT_UNSUBSCRIBE_SUCCESS_VALUES_ENV
                + " must be a comma-separated exact integer set"
            )
        values.add(int(value))
    return frozenset(values)


def _journal_safe(value: Any, *, depth: int = 0) -> Any:
    if depth > 8:
        return "[depth-limit]"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        return {
            str(key)[:256]: _journal_safe(item, depth=depth + 1)
            for key, item in list(mapping.items())[:256]
            if str(key) != "leaseToken"
        }
    if isinstance(value, (list, tuple)):
        sequence = cast(Sequence[Any], value)
        return [_journal_safe(item, depth=depth + 1) for item in sequence[:256]]
    return str(value)[:1024]


def _encode_record(record: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65_536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_text_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _archive_sort_key(path: Path) -> tuple[int, int]:
    parts = path.name.rsplit(".", 3)
    try:
        return int(parts[-3]), int(parts[-2])
    except (ValueError, IndexError):
        return (0, 0)
