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
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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
MAX_CONTEXT_REBUILD_OBSERVATION_BYTES = 16_384
MIN_ROTATION_OVERHEAD_BYTES = MAX_JOURNAL_RECORD_BYTES * 2
DEFAULT_CONTROL_TIMEOUT_SECONDS = 10.0
DEFAULT_FALSE_UNSUBSCRIBE_VERIFY_SECONDS = 2.0
DEFAULT_CALLBACK_FRESH_SECONDS = 5.0
CONTROL_COMPLETION_MARGIN_SECONDS = 0.25
QMT_UNSUBSCRIBE_SUCCESS_VALUES_ENV = "MIST_QMT_UNSUBSCRIBE_SUCCESS_VALUES"
QMT_CONTEXT_REBUILD_OBSERVATION_PATH_ENV = (
    "MIST_QMT_CONTEXT_REBUILD_OBSERVATION_PATH"
)
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
        if ("whole", None, subscription_id) in self.retained_recovery:
            return False
        if ("single", symbol, subscription_id) in self.retained_recovery:
            return False
        if self.whole is not None and self.whole.sub_id == subscription_id:
            return symbol in self.whole.symbols
        return self.singles.get(symbol) == subscription_id

    def contains_symbol(self, symbol: str) -> bool:
        return self.whole is not None and symbol in self.whole.symbols or symbol in self.singles

    def current_subscription_ids(self) -> set[int]:
        subscription_ids = set(self.singles.values())
        if self.whole is not None:
            subscription_ids.add(self.whole.sub_id)
        return {
            subscription_id
            for subscription_id in subscription_ids
            if not any(
                retained_id == subscription_id
                for _bucket, _symbol, retained_id in self.retained_recovery
            )
        }


class QmtSubscriptionJournal:
    """Single-writer append-only JSONL journal with bounded rotation."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        rotate_bytes: int | str | None = None,
        archive_max_bytes: int | str | None = None,
        resolved_retention_days: int | str | None = None,
        wall_clock: Callable[[], datetime] | None = None,
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
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        self._record_sequence = 0
        self._previous_hash = "0" * 64
        self._archive_index = 0
        self.healthy = True
        self.last_error: str | None = None
        self.last_rotation_at: str | None = None
        self.last_compaction_at: str | None = None
        self._checkpoint_sequence = 0
        self._last_record: dict[str, Any] | None = None
        self._recover_interrupted_rotation()
        self._recover_interrupted_compaction()
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
                self._last_record = record
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
        total_bytes = self._total_bytes()
        if total_bytes + next_bytes > self.archive_max_bytes:
            self._compact_resolved_archives()
            total_bytes = self._total_bytes()
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
        _durable_replace(self.path, rotating)
        first_sequence = _first_record_sequence(rotating)
        archive_name = (
            self.path.name
            + "."
            + str(first_sequence)
            + "-"
            + str(self._record_sequence)
            + "."
            + str(self._archive_index + 1)
            + ".jsonl"
        )
        archive = self.path.with_name(archive_name)
        _durable_replace(rotating, archive)
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
        _atomic_bytes_write(self.path, encoded)
        self._record_sequence = cast(int, anchor["sequence"])
        self._previous_hash = cast(str, anchor["hash"])
        self._last_record = anchor
        self.last_rotation_at = datetime.now(UTC).isoformat()

    def compact(self) -> bool:
        """Compact a fully resolved archive prefix under the single-writer lock."""
        with self._lock:
            return self._compact_resolved_archives()

    def _compact_resolved_archives(self) -> bool:
        archives = self._archive_paths()
        compactable = _resolved_archive_prefix(archives)
        if not compactable:
            return False
        first_sequence = _first_record_sequence(compactable[0])
        last_sequence, last_hash = _last_record_identity(compactable[-1])
        checkpoint_path = self.path.with_name(
            self.path.name
            + ".compaction-checkpoint."
            + str(first_sequence)
            + "-"
            + str(last_sequence)
            + ".json"
        )
        source_entries = [
            {
                "name": archive.name,
                "sha256": _sha256_file(archive),
                "bytes": archive.stat().st_size,
            }
            for archive in compactable
        ]
        previous_checkpoint = self._latest_checkpoint()
        checkpoint = {
            "kind": "compaction_checkpoint",
            "createdAt": self._wall_clock().isoformat(),
            "firstSequence": first_sequence,
            "lastSequence": last_sequence,
            "lastRecordHash": last_hash,
            "sourceArchives": source_entries,
            "resolvedLifecycles": _resolved_lifecycle_summaries(compactable),
            "previousCheckpointSha256": (
                _sha256_file(previous_checkpoint) if previous_checkpoint else None
            ),
        }
        marker_path = self._maintenance_marker_path()
        marker = {
            "operation": "compaction",
            "phase": "prepared",
            "checkpoint": checkpoint_path.name,
            "sources": [item.name for item in compactable],
        }
        _atomic_json_write(marker_path, marker)
        _atomic_json_write(checkpoint_path, checkpoint)
        marker["phase"] = "checkpoint_published"
        _atomic_json_write(marker_path, marker)
        self._publish_catalog(checkpoint_path)
        marker["phase"] = "manifest_published"
        _atomic_json_write(marker_path, marker)
        for archive in compactable:
            archive.unlink()
            sidecar = archive.with_suffix(archive.suffix + ".sha256")
            if sidecar.exists():
                sidecar.unlink()
        _fsync_directory(self.path.parent)
        marker["phase"] = "sources_retired"
        _atomic_json_write(marker_path, marker)
        marker_path.unlink()
        _fsync_directory(self.path.parent)
        self.last_compaction_at = self._wall_clock().isoformat()
        self._fold_expired_checkpoints()
        return True

    def _recover_interrupted_compaction(self) -> None:
        marker_path = self._maintenance_marker_path()
        if not marker_path.exists():
            return
        try:
            marker = cast(dict[str, Any], json.loads(marker_path.read_text(encoding="utf-8")))
            checkpoint = self.path.with_name(str(marker["checkpoint"]))
            sources = [self.path.with_name(str(name)) for name in marker.get("sources", [])]
            phase = str(marker.get("phase", ""))
            if phase == "prepared" and not checkpoint.exists():
                marker_path.unlink()
                _fsync_directory(self.path.parent)
                return
            if not checkpoint.exists():
                raise QmtSubscriptionJournalError(
                    "QMT journal compaction checkpoint is missing"
                )
            checkpoint_value = cast(
                dict[str, Any], json.loads(checkpoint.read_text(encoding="utf-8"))
            )
            expected = {
                str(item["name"]): str(item["sha256"])
                for item in checkpoint_value.get("sourceArchives", [])
            }
            for source in sources:
                if source.exists() and _sha256_file(source) != expected.get(source.name):
                    raise QmtSubscriptionJournalError(
                        "QMT journal compaction source checksum mismatch"
                    )
            self._publish_catalog(checkpoint)
            for source in sources:
                if source.exists():
                    source.unlink()
                sidecar = source.with_suffix(source.suffix + ".sha256")
                if sidecar.exists():
                    sidecar.unlink()
            marker_path.unlink()
            _fsync_directory(self.path.parent)
        except Exception as exc:
            if isinstance(exc, QmtSubscriptionJournalError):
                raise
            raise QmtSubscriptionJournalError(
                "QMT journal compaction recovery failed: " + str(exc)
            ) from exc

    def _publish_catalog(self, checkpoint: Path) -> None:
        checkpoint_value = cast(
            dict[str, Any], json.loads(checkpoint.read_text(encoding="utf-8"))
        )
        _atomic_json_write(
            self.path.with_name(self.path.name + ".catalog.json"),
            {
                "latestCheckpoint": checkpoint.name,
                "latestCheckpointSha256": _sha256_file(checkpoint),
                "lastSequence": checkpoint_value["lastSequence"],
                "lastRecordHash": checkpoint_value["lastRecordHash"],
            },
        )

    def _fold_expired_checkpoints(self) -> None:
        checkpoints = self._checkpoint_paths()
        if len(checkpoints) < 2:
            return
        cutoff = self._wall_clock() - timedelta(days=self.resolved_retention_days)
        expired: list[Path] = []
        for checkpoint in checkpoints[:-1]:
            value = cast(dict[str, Any], json.loads(checkpoint.read_text(encoding="utf-8")))
            created_at = datetime.fromisoformat(str(value["createdAt"]))
            if created_at < cutoff:
                expired.append(checkpoint)
        if not expired:
            return
        checkpoint_digests = [_sha256_file(item) for item in expired]
        previous_folds = sorted(
            self.path.parent.glob(self.path.name + ".compaction-fold.*.json"),
            key=_checkpoint_sort_key,
        )
        prior_sealed_digest = _sha256_file(previous_folds[-1]) if previous_folds else None
        first = cast(
            dict[str, Any], json.loads(expired[0].read_text(encoding="utf-8"))
        )
        last = cast(
            dict[str, Any], json.loads(expired[-1].read_text(encoding="utf-8"))
        )
        fold_path = self.path.with_name(
            self.path.name
            + ".compaction-fold."
            + str(first["firstSequence"])
            + "-"
            + str(last["lastSequence"])
            + ".json"
        )
        root_payload = {
            "priorSealedCheckpointDigest": prior_sealed_digest,
            "retiredCheckpointDigests": checkpoint_digests,
        }
        sealed_root = hashlib.sha256(
            json.dumps(root_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        resolved_count = sum(
            len(
                cast(
                    dict[str, Any],
                    json.loads(item.read_text(encoding="utf-8")),
                ).get("resolvedLifecycles", [])
            )
            for item in expired
        )
        _atomic_json_write(
            fold_path,
            {
                "kind": "resolved_lifecycle_fold",
                "createdAt": self._wall_clock().isoformat(),
                "firstSequence": first["firstSequence"],
                "lastSequence": last["lastSequence"],
                "lastRecordHash": last["lastRecordHash"],
                "resolvedLifecycleCount": resolved_count,
                "priorSealedCheckpointDigest": prior_sealed_digest,
                "sealedRootSha256": sealed_root,
            },
        )
        for checkpoint in expired:
            checkpoint.unlink()
        _fsync_directory(self.path.parent)

    def _archive_paths(self) -> list[Path]:
        return sorted(
            self.path.parent.glob(self.path.name + ".*.*.jsonl"),
            key=_archive_sort_key,
        )

    def _checkpoint_paths(self) -> list[Path]:
        return sorted(
            self.path.parent.glob(self.path.name + ".compaction-checkpoint.*.json"),
            key=_checkpoint_sort_key,
        )

    def _latest_checkpoint(self) -> Path | None:
        checkpoints = self._checkpoint_paths()
        return checkpoints[-1] if checkpoints else None

    def _maintenance_marker_path(self) -> Path:
        return self.path.with_name(self.path.name + ".maintenance.json")

    def _total_bytes(self) -> int:
        return sum(
            item.stat().st_size
            for item in self.path.parent.glob(self.path.name + "*")
            if item.is_file()
        )

    def _recover_interrupted_rotation(self) -> None:
        rotating = self.path.with_name(self.path.name + ".rotating")
        temporary = self.path.with_name(self.path.name + ".tmp")
        if temporary.exists():
            temporary.unlink()
            _fsync_directory(self.path.parent)
        if rotating.exists():
            if self.path.exists():
                raise QmtSubscriptionJournalError(
                    "ambiguous QMT subscription journal rotation state"
                )
            _durable_replace(rotating, self.path)
            return
        if self.path.exists():
            return

        archives = self._archive_paths()
        if not archives:
            return
        archive = archives[-1]
        archive_digest = _sha256_file(archive)
        sidecar = archive.with_suffix(archive.suffix + ".sha256")
        _atomic_text_write(sidecar, archive_digest + "  " + archive.name + "\n")
        last_sequence, last_hash = _last_record_identity(archive)
        _atomic_json_write(
            self.path.with_name(self.path.name + ".manifest.json"),
            {
                "archive": archive.name,
                "sha256": archive_digest,
                "lastRecordSequence": last_sequence,
                "previousHash": last_hash,
            },
        )
        self._record_sequence = last_sequence
        self._previous_hash = last_hash
        anchor = self._build_record(
            "rotation_anchor",
            {
                "archive": archive.name,
                "archiveSha256": archive_digest,
                "lastRecordSequence": last_sequence,
            },
        )
        _atomic_bytes_write(self.path, _encode_record(anchor))
        self._record_sequence = 0
        self._previous_hash = "0" * 64

    def _load_tail(self) -> None:
        archives = self._archive_paths()
        paths = [*archives]
        if self.path.exists():
            paths.append(self.path)
        if not paths:
            return
        try:
            checkpoint = self._latest_checkpoint()
            if checkpoint is None:
                expected_sequence = 1
                previous_hash = "0" * 64
            else:
                checkpoint_value = cast(
                    dict[str, Any],
                    json.loads(checkpoint.read_text(encoding="utf-8")),
                )
                expected_sequence = int(checkpoint_value["lastSequence"]) + 1
                previous_hash = str(checkpoint_value["lastRecordHash"])
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
                        self._last_record = record
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
            "lastCompactionAt": self.last_compaction_at,
            "checkpointCount": len(self._checkpoint_paths()),
        }

    @property
    def record_sequence(self) -> int:
        return self._record_sequence

    @property
    def last_record(self) -> dict[str, Any] | None:
        return dict(self._last_record) if self._last_record is not None else None


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
        false_unsubscribe_verify_seconds: float = DEFAULT_FALSE_UNSUBSCRIBE_VERIFY_SECONDS,
        callback_fresh_seconds: float = DEFAULT_CALLBACK_FRESH_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.registry = QmtSubscriptionRegistry()
        self.journal = journal
        self._owner_validator = owner_validator
        self._publisher = publisher
        self._unsubscribe_success_values = unsubscribe_success_values
        self._timeout_seconds = timeout_seconds
        self._false_unsubscribe_verify_seconds = max(
            0.0, false_unsubscribe_verify_seconds
        )
        self._callback_fresh_seconds = max(0.0, callback_fresh_seconds)
        self._clock = clock
        self._mutation_lock = asyncio.Lock()
        self._slot: _NativeSlot | None = None
        self._call_sequence = 0
        self._callback_counts: dict[int, int] = {}
        self._callback_last_seen: dict[int, float] = {}
        self._callback_event = asyncio.Event()
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
        if any(
            QMT_SYMBOL_PATTERN.fullmatch(str(raw_symbol).strip().upper())
            and self.registry.owns(
                subscription_id, str(raw_symbol).strip().upper()
            )
            for raw_symbol in native
        ):
            self._callback_counts[subscription_id] = (
                self._callback_counts.get(subscription_id, 0) + 1
            )
            self._callback_last_seen[subscription_id] = self._clock()
            self._callback_event.set()
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
            "callbackObservedHandleCount": len(self._callback_last_seen),
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

    def observe_rebuilt_context(
        self,
        *,
        affected_journal_sequence: int | None = None,
        operator_evidence_digest: str = "0" * 64,
        observation_time: str | None = None,
        recovery_mode: str = "qmt_context_rebuilt",
    ) -> None:
        """Unlock only after a durable, operator-proven QMT context rebuild."""
        affected_sequence = (
            self.journal.record_sequence
            if affected_journal_sequence is None
            else affected_journal_sequence
        )
        if affected_sequence != self.journal.record_sequence:
            raise QmtSubscriptionJournalError(
                "QMT context rebuild observation is stale"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", operator_evidence_digest):
            raise QmtSubscriptionJournalError(
                "QMT context rebuild evidence digest must be lowercase SHA-256"
            )
        observed_at = observation_time or datetime.now(UTC).isoformat()
        if not RFC3339_PATTERN.fullmatch(observed_at):
            raise QmtSubscriptionJournalError(
                "QMT context rebuild observation time must be RFC3339"
            )
        self.journal.append(
            "operator_observation",
            {
                "affectedJournalSequence": affected_sequence,
                "recoveryMode": recovery_mode,
                "operatorEvidenceDigest": operator_evidence_digest,
                "observationTime": observed_at,
                "physicalSubscriptionsAssumedReleased": True,
            },
        )
        self.registry = QmtSubscriptionRegistry()
        self.reconciliation_required = False

    def consume_rebuilt_context_observation(self, path: str | Path) -> None:
        """Consume one protected one-shot recovery observation before serving."""
        observation_path = Path(path)
        processing_path = observation_path.with_name(observation_path.name + ".processing")
        if observation_path.exists() and processing_path.exists():
            raise QmtSubscriptionJournalError(
                "ambiguous QMT context rebuild observation state"
            )
        if observation_path.exists():
            if observation_path.stat().st_size > MAX_CONTEXT_REBUILD_OBSERVATION_BYTES:
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild observation exceeds bounded size"
                )
            _durable_replace(observation_path, processing_path)
        if not processing_path.exists():
            return

        try:
            raw = processing_path.read_bytes()
            if len(raw) > MAX_CONTEXT_REBUILD_OBSERVATION_BYTES:
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild observation exceeds bounded size"
                )
            decoded: object = json.loads(raw.decode("utf-8-sig"))
            if not isinstance(decoded, dict):
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild observation has invalid fields"
                )
            value = cast(dict[str, object], decoded)
            if set(value.keys()) != {
                "schemaVersion",
                "observation",
                "affectedJournalSequence",
                "recoveryMode",
                "operatorEvidenceDigest",
                "observationTime",
            }:
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild observation has invalid fields"
                )
            if value["schemaVersion"] != 1 or value["observation"] != "qmt_context_rebuilt":
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild observation has invalid identity"
                )
            affected_value = value["affectedJournalSequence"]
            if type(affected_value) is not int or affected_value < 0:
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild affected sequence must be a non-negative integer"
                )
            affected_sequence = affected_value
            recovery_mode = value["recoveryMode"]
            evidence_digest = value["operatorEvidenceDigest"]
            observation_time = value["observationTime"]
            if (
                not isinstance(recovery_mode, str)
                or recovery_mode != "terminal_process_restarted"
                or not isinstance(evidence_digest, str)
                or not isinstance(observation_time, str)
            ):
                raise QmtSubscriptionJournalError(
                    "QMT context rebuild observation has invalid recovery evidence"
                )
            detail: dict[str, Any] = {
                "affectedJournalSequence": affected_sequence,
                "recoveryMode": recovery_mode,
                "operatorEvidenceDigest": evidence_digest,
                "observationTime": observation_time,
                "physicalSubscriptionsAssumedReleased": True,
            }
            last_record = self.journal.last_record
            already_durable = (
                last_record is not None
                and last_record.get("kind") == "operator_observation"
                and last_record.get("detail") == detail
            )
            if not already_durable:
                self.observe_rebuilt_context(
                    affected_journal_sequence=affected_sequence,
                    recovery_mode=recovery_mode,
                    operator_evidence_digest=evidence_digest,
                    observation_time=observation_time,
                )
            else:
                self.registry = QmtSubscriptionRegistry()
                self.reconciliation_required = False
            processing_path.unlink()
            _fsync_directory(processing_path.parent)
        except QmtSubscriptionJournalError:
            raise
        except Exception as exc:
            raise QmtSubscriptionJournalError(
                "QMT context rebuild observation is invalid: " + str(exc)
            ) from exc

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
        self._reset_callback_observation(sub_id)
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
        self._reset_callback_observation(sub_id)
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
        call_started_at = self._clock()
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
        confirmed_by: str | None = None
        if (
            reply.success_present
            and type(reply.success) is int
            and reply.success in self._unsubscribe_success_values
        ):
            confirmed_by = "hil_integer"
        elif (
            reply.success_present
            and type(reply.success) is bool
            and reply.success is False
            and await self._verify_false_unsubscribe(
                sub_id=sub_id,
                call_started_at=call_started_at,
            )
        ):
            confirmed_by = "callback_silence_with_live_witness"
        if confirmed_by is None:
            return QmtSubscriptionControlError(
                "QMT_UNSUBSCRIBE_UNCONFIRMED",
                symbol=symbol,
                subscription_state="unknown",
            )
        if not durable or not self._append_transition(
            "unsubscribed",
            {
                "bucket": bucket,
                "symbol": symbol,
                "subId": sub_id,
                "confirmedBy": confirmed_by,
            },
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
        self._forget_callback_observation(sub_id)
        return None

    def _reset_callback_observation(self, sub_id: int) -> None:
        self._callback_counts[sub_id] = 0
        self._callback_last_seen.pop(sub_id, None)

    def _forget_callback_observation(self, sub_id: int) -> None:
        self._callback_counts.pop(sub_id, None)
        self._callback_last_seen.pop(sub_id, None)

    async def _verify_false_unsubscribe(
        self,
        *,
        sub_id: int,
        call_started_at: float,
    ) -> bool:
        last_seen = self._callback_last_seen.get(sub_id)
        if (
            last_seen is None
            or call_started_at - last_seen > self._callback_fresh_seconds
        ):
            return False
        witness_ids = self.registry.current_subscription_ids() - {sub_id}
        if not witness_ids or self._false_unsubscribe_verify_seconds <= 0:
            return False
        target_baseline = self._callback_counts.get(sub_id, 0)
        witness_baseline = {
            witness_id: self._callback_counts.get(witness_id, 0)
            for witness_id in witness_ids
        }
        deadline = min(
            self._clock() + self._false_unsubscribe_verify_seconds,
            call_started_at
            + self._timeout_seconds
            - CONTROL_COMPLETION_MARGIN_SECONDS,
        )
        if deadline <= self._clock():
            return False
        while True:
            if self._callback_counts.get(sub_id, 0) > target_baseline:
                return False
            now = self._clock()
            if now >= deadline:
                return any(
                    self._callback_counts.get(witness_id, 0) > baseline
                    for witness_id, baseline in witness_baseline.items()
                )
            self._callback_event.clear()
            if self._callback_counts.get(sub_id, 0) > target_baseline:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._callback_event.wait(),
                    timeout=max(0.0, deadline - now),
                )

    async def _native_call(
        self,
        method: NativeMethod,
        fields: dict[str, Any],
    ) -> tuple[QmtNativeReply, bool]:
        command_symbol = fields.get("symbol")
        if not isinstance(command_symbol, str):
            command_symbol = None
        if self._slot is not None:
            raise QmtSubscriptionControlError(
                "QMT_SUBSCRIPTION_CONTROL_BUSY",
                symbol=command_symbol,
            )
        call_sequence = self._call_sequence + 1
        command = {"callSequence": call_sequence, "method": method, **fields}
        try:
            self.journal.append(
                "native_intent",
                {"callSequence": call_sequence, "method": method, **fields},
            )
        except QmtSubscriptionJournalError as exc:
            raise QmtSubscriptionControlError(
                "QMT_JOURNAL_DURABILITY_FAILED",
                symbol=command_symbol,
            ) from exc
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
                raise QmtSubscriptionControlError(
                    "QMT_SUBSCRIPTION_CALL_TIMEOUT",
                    symbol=command_symbol,
                ) from exc
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
    _durable_replace(temporary, path)


def _atomic_text_write(path: Path, value: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    _durable_replace(temporary, path)


def _atomic_bytes_write(path: Path, value: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    _durable_replace(temporary, path)


def _archive_sort_key(path: Path) -> tuple[int, int]:
    match = re.search(r"\.(\d+)-(\d+)\.(\d+)\.jsonl$", path.name)
    if match:
        return int(match.group(1)), int(match.group(3))
    parts = path.name.rsplit(".", 3)
    try:
        return int(parts[-3]), int(parts[-2])
    except (ValueError, IndexError):
        return (0, 0)


def _checkpoint_sort_key(path: Path) -> tuple[int, int]:
    match = re.search(r"\.(\d+)-(\d+)\.json$", path.name)
    if match:
        return int(match.group(1)), int(match.group(2))
    return (0, 0)


def _read_journal_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(cast(dict[str, Any], json.loads(line)))
    return records


def _first_record_sequence(path: Path) -> int:
    records = _read_journal_records(path)
    if not records:
        raise QmtSubscriptionJournalError("QMT journal archive is empty")
    return int(records[0]["sequence"])


def _last_record_identity(path: Path) -> tuple[int, str]:
    records = _read_journal_records(path)
    if not records:
        raise QmtSubscriptionJournalError("QMT journal archive is empty")
    return int(records[-1]["sequence"]), str(records[-1]["hash"])


def _resolved_archive_prefix(archives: Sequence[Path]) -> list[Path]:
    """Return the longest contiguous archive prefix safe to replace.

    The scanner is deliberately conservative: every native call must reach a
    matching durable registry transition and every created handle must be
    durably unsubscribed (or cleared by an operator context-rebuild
    observation) at the selected archive boundary.
    """
    pending: dict[int, dict[str, Any]] = {}
    awaiting_transition: dict[int, dict[str, Any]] = {}
    open_handles: set[tuple[str, str | None, int]] = set()
    compactable_count = 0
    for archive_index, archive in enumerate(archives, start=1):
        for record in _read_journal_records(archive):
            kind = record.get("kind")
            detail_value = record.get("detail")
            if not isinstance(detail_value, dict):
                continue
            detail = cast(dict[str, Any], detail_value)
            if kind == "native_intent":
                sequence = detail.get("callSequence")
                if type(sequence) is int:
                    pending[sequence] = detail
            elif kind == "native_result":
                sequence = detail.get("callSequence")
                sequence_int = sequence if isinstance(sequence, int) and not isinstance(sequence, bool) else None
                intent = pending.pop(sequence_int, None) if sequence_int is not None else None
                if (
                    intent is not None
                    and detail.get("failure") is None
                    and detail.get("successPresent") is True
                    and sequence_int is not None
                ):
                    awaiting_transition[sequence_int] = intent
            elif kind == "registry_transition":
                transition = detail.get("transition")
                sub_id = detail.get("subId")
                symbol = detail.get("symbol")
                if type(sub_id) is not int:
                    continue
                if transition == "single_subscribed":
                    open_handles.add(("single", str(symbol), sub_id))
                    _consume_transition(awaiting_transition, "subscribe_quote", sub_id)
                elif transition == "whole_subscribed":
                    open_handles.add(("whole", None, sub_id))
                    _consume_transition(awaiting_transition, "subscribe_whole_quote", sub_id)
                elif transition == "unsubscribed":
                    bucket = str(detail.get("bucket"))
                    normalized_symbol = str(symbol) if isinstance(symbol, str) else None
                    open_handles.discard((bucket, normalized_symbol, sub_id))
                    _consume_transition(awaiting_transition, "unsubscribe_quote", sub_id)
            elif (
                kind == "operator_observation"
                and detail.get("observation") == "qmt_context_rebuilt"
            ):
                pending.clear()
                awaiting_transition.clear()
                open_handles.clear()
        if not pending and not awaiting_transition and not open_handles:
            compactable_count = archive_index
    return list(archives[:compactable_count])


def _resolved_lifecycle_summaries(archives: Sequence[Path]) -> list[dict[str, Any]]:
    archive_digest_by_sequence: dict[int, str] = {}
    records: list[dict[str, Any]] = []
    for archive in archives:
        digest = _sha256_file(archive)
        for record in _read_journal_records(archive):
            sequence = int(record.get("sequence", -1))
            archive_digest_by_sequence[sequence] = digest
            records.append(record)
    opened: dict[tuple[str, str | None, int], dict[str, Any]] = {}
    resolved: list[dict[str, Any]] = []
    for record in records:
        if record.get("kind") != "registry_transition":
            if (
                record.get("kind") == "operator_observation"
                and isinstance(record.get("detail"), dict)
                and cast(dict[str, Any], record["detail"]).get("observation")
                == "qmt_context_rebuilt"
            ):
                for _key, lifecycle in sorted(opened.items(), key=lambda item: repr(item[0])):
                    resolved.append(
                        {
                            **lifecycle,
                            "lastSequence": record["sequence"],
                            "terminalRecordHash": record["hash"],
                            "terminalArchiveSha256": archive_digest_by_sequence[
                                int(record["sequence"])
                            ],
                            "terminal": "operator_context_rebuilt",
                        }
                    )
                opened.clear()
            continue
        detail_value = record.get("detail")
        if not isinstance(detail_value, dict):
            continue
        detail = cast(dict[str, Any], detail_value)
        transition = detail.get("transition")
        sub_id = detail.get("subId")
        if type(sub_id) is not int:
            continue
        if transition == "single_subscribed":
            key = ("single", str(detail.get("symbol")), sub_id)
            opened[key] = {
                "subId": sub_id,
                "bucket": "single",
                "symbol": str(detail.get("symbol")),
                "firstSequence": record["sequence"],
            }
        elif transition == "whole_subscribed":
            key = ("whole", None, sub_id)
            opened[key] = {
                "subId": sub_id,
                "bucket": "whole",
                "symbol": None,
                "firstSequence": record["sequence"],
            }
        elif transition == "unsubscribed":
            bucket = str(detail.get("bucket"))
            symbol = detail.get("symbol") if isinstance(detail.get("symbol"), str) else None
            lifecycle = opened.pop((bucket, symbol, sub_id), None)
            if lifecycle is not None:
                resolved.append(
                    {
                        **lifecycle,
                        "lastSequence": record["sequence"],
                        "terminalRecordHash": record["hash"],
                        "terminalArchiveSha256": archive_digest_by_sequence[
                            int(record["sequence"])
                        ],
                        "terminal": "unsubscribed",
                    }
                )
    return resolved


def _consume_transition(
    awaiting_transition: dict[int, dict[str, Any]],
    method: str,
    sub_id: int,
) -> None:
    for sequence, intent in list(awaiting_transition.items()):
        if intent.get("method") != method:
            continue
        if method == "unsubscribe_quote" and intent.get("subId") != sub_id:
            continue
        awaiting_transition.pop(sequence, None)
        return


def _durable_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        import ctypes

        movefile_replace_existing = 0x1
        movefile_write_through = 0x8
        succeeded = ctypes.windll.kernel32.MoveFileExW(
            str(source),
            str(target),
            movefile_replace_existing | movefile_write_through,
        )
        if not succeeded:
            raise OSError(ctypes.get_last_error(), "MoveFileExW failed")
    else:
        os.replace(source, target)
        _fsync_directory(target.parent)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
