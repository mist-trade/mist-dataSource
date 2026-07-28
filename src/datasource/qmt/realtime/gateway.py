"""QMT realtime command gateway and owner lifecycle."""

import json
import math
import secrets
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

DEFAULT_MAX_OUTSTANDING_COMMANDS = 64
DEFAULT_MAX_RETAINED_RESULTS = 64
DEFAULT_RESULT_TTL_SECONDS = 300.0
DEFAULT_MAX_POLL_LIMIT = 16
DEFAULT_MAX_COMMAND_BYTES = 65_536
DEFAULT_MAX_RESULT_BYTES = 8_388_608
DEFAULT_MAX_RETAINED_RESULT_BYTES = 33_554_432
TERMINAL_RESULT_RESERVATION_BYTES = 1_024
QMT_COMMAND_REJECTION_REASONS = (
    "capacity",
    "command_invalid",
    "command_too_large",
    "result_capacity",
    "result_invalid",
    "result_too_large",
)


class QmtBridgeOwnershipError(Exception):
    """Raised when a non-owner bridge attempts to process QMT commands."""


class QmtCommandTimeoutError(Exception):
    """Raised when a QMT command has already timed out."""


class QmtCommandRejectedError(Exception):
    """Raised before a historical command can be safely accepted."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        http_status: int,
        retryable: bool,
        details: dict[str, Any],
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.retryable = retryable
        self.details = details

    def as_detail(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
            "details": self.details,
        }


@dataclass(frozen=True)
class QmtBridgeOwner:
    owner_id: str
    lease_token: str
    registered_at: float
    last_heartbeat_at: float
    generation: int
    bridge_build_id: str
    bridge_artifact_sha256: str
    bridge_runtime_fingerprint: str


@dataclass(frozen=True)
class QmtCommand:
    command_id: str
    method: str
    params: dict[str, Any]
    created_at: float
    timeout_seconds: float


@dataclass(frozen=True)
class QmtCommandResult:
    command_id: str
    ok: bool
    completed_at: float
    result: Any | None = None
    error: dict[str, Any] | None = None


@dataclass
class _InFlightCommand:
    command: QmtCommand
    claimed_at: float
    owner_generation: int


@dataclass(frozen=True)
class _StoredResult:
    result: QmtCommandResult
    encoded_bytes: int
    expires_at: float


class QmtCommandGateway:
    """In-memory command gateway for the single-owner full-QMT bridge."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        default_timeout_seconds: float = 10.0,
        owner_stale_after_seconds: float = 15.0,
        max_outstanding_commands: int = DEFAULT_MAX_OUTSTANDING_COMMANDS,
        max_retained_results: int = DEFAULT_MAX_RETAINED_RESULTS,
        result_ttl_seconds: float = DEFAULT_RESULT_TTL_SECONDS,
        max_poll_limit: int = DEFAULT_MAX_POLL_LIMIT,
        max_command_bytes: int = DEFAULT_MAX_COMMAND_BYTES,
        max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES,
        max_retained_result_bytes: int = DEFAULT_MAX_RETAINED_RESULT_BYTES,
    ) -> None:
        self._clock = clock or _monotonic_seconds
        self._default_timeout_seconds = _positive_finite(
            "default_timeout_seconds", default_timeout_seconds
        )
        self._owner_stale_after_seconds = _positive_finite(
            "owner_stale_after_seconds", owner_stale_after_seconds
        )
        self._max_outstanding_commands = _positive_int(
            "max_outstanding_commands", max_outstanding_commands
        )
        self._max_retained_results = _positive_int(
            "max_retained_results", max_retained_results
        )
        self._result_ttl_seconds = _positive_finite(
            "result_ttl_seconds", result_ttl_seconds
        )
        self._max_poll_limit = _positive_int("max_poll_limit", max_poll_limit)
        self._max_command_bytes = _positive_int(
            "max_command_bytes", max_command_bytes
        )
        self._max_result_bytes = _positive_int("max_result_bytes", max_result_bytes)
        self._max_retained_result_bytes = _positive_int(
            "max_retained_result_bytes", max_retained_result_bytes
        )
        if self._max_retained_results < self._max_outstanding_commands:
            raise ValueError(
                "max_retained_results must be >= max_outstanding_commands"
            )
        if (
            self._max_retained_result_bytes
            < self._max_retained_results * TERMINAL_RESULT_RESERVATION_BYTES
        ):
            raise ValueError(
                "max_retained_result_bytes cannot reserve every terminal result"
            )
        self._owner: QmtBridgeOwner | None = None
        self._pending: deque[QmtCommand] = deque()
        self._in_flight: dict[str, _InFlightCommand] = {}
        self._results: dict[str, _StoredResult] = {}
        self._retained_result_bytes = 0
        self._rejection_totals: dict[str, int] = dict.fromkeys(
            QMT_COMMAND_REJECTION_REASONS,
            0,
        )

    def register_owner(
        self,
        owner_id: str,
        *,
        bridge_build_id: str = "unknown",
        bridge_artifact_sha256: str = "unknown",
        bridge_runtime_fingerprint: str = "unknown",
    ) -> QmtBridgeOwner:
        now = self._clock()
        previous = self._owner
        stale = self._owner_is_stale(now)
        if previous is not None and previous.owner_id != owner_id and not stale:
            raise QmtBridgeOwnershipError(
                f"QMT bridge owner already registered: {previous.owner_id}"
            )
        replacing = previous is not None and (previous.owner_id != owner_id or stale)
        if replacing:
            self._fail_commands_for_replaced_owner(now)
        if previous is not None and previous.owner_id == owner_id and not stale:
            lease_token = previous.lease_token
            generation = previous.generation
            registered_at = previous.registered_at
        else:
            lease_token = "lease-" + secrets.token_urlsafe(24)
            generation = previous.generation + 1 if previous else 1
            registered_at = now
        self._owner = QmtBridgeOwner(
            owner_id=owner_id,
            lease_token=lease_token,
            registered_at=registered_at,
            last_heartbeat_at=now,
            generation=generation,
            bridge_build_id=bridge_build_id,
            bridge_artifact_sha256=bridge_artifact_sha256,
            bridge_runtime_fingerprint=bridge_runtime_fingerprint,
        )
        return self._owner

    def heartbeat(
        self, owner_id: str, lease_token: str | None = None, generation: int | None = None
    ) -> QmtBridgeOwner:
        self._require_owner(owner_id, lease_token, generation)
        assert self._owner is not None
        self._owner = QmtBridgeOwner(
            owner_id=self._owner.owner_id,
            lease_token=self._owner.lease_token,
            registered_at=self._owner.registered_at,
            last_heartbeat_at=self._clock(),
            generation=self._owner.generation,
            bridge_build_id=self._owner.bridge_build_id,
            bridge_artifact_sha256=self._owner.bridge_artifact_sha256,
            bridge_runtime_fingerprint=self._owner.bridge_runtime_fingerprint,
        )
        return self._owner

    def validate_owner(self, owner_id: str, lease_token: str, generation: int) -> None:
        """Validate and heartbeat the current bridge lease without exposing its token."""
        self._require_owner(owner_id, lease_token, generation)
        self.heartbeat(owner_id, lease_token, generation)

    def enqueue(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> QmtCommand:
        now = self._clock()
        self._maintain(now)
        timeout = (
            self._default_timeout_seconds
            if timeout_seconds is None
            else _positive_finite("timeout_seconds", timeout_seconds)
        )
        try:
            command_bytes = _json_bytes(
                {
                    "method": method,
                    "params": params,
                    "timeoutSeconds": timeout,
                }
            )
        except (TypeError, ValueError) as exc:
            self._reject(
                reason="command_invalid",
                code="QMT_COMMAND_PAYLOAD_INVALID",
                message="QMT command payload is not finite JSON",
                http_status=413,
                details={"method": _bounded_method(method)},
            )
            raise AssertionError("unreachable") from exc
        if command_bytes > self._max_command_bytes:
            self._reject(
                reason="command_too_large",
                code="QMT_COMMAND_PAYLOAD_TOO_LARGE",
                message="QMT command payload exceeds the byte limit",
                http_status=413,
                details={
                    "method": _bounded_method(method),
                    "actualBytes": command_bytes,
                    "maxBytes": self._max_command_bytes,
                },
            )
        outstanding = self._outstanding_count()
        result_slots_used = len(self._results) + outstanding
        reserved_result_bytes = (
            self._retained_result_bytes
            + (outstanding + 1) * TERMINAL_RESULT_RESERVATION_BYTES
        )
        if (
            outstanding >= self._max_outstanding_commands
            or result_slots_used >= self._max_retained_results
            or reserved_result_bytes > self._max_retained_result_bytes
        ):
            self._reject(
                reason="capacity",
                code="QMT_COMMAND_CAPACITY_EXCEEDED",
                message="QMT command gateway has no terminal-result capacity",
                http_status=429,
                details=self._capacity_details(),
            )
        command = QmtCommand(
            command_id=str(uuid4()),
            method=method,
            params=dict(params),
            created_at=now,
            timeout_seconds=timeout,
        )
        self._pending.append(command)
        return command

    def poll(
        self,
        owner_id: str,
        *,
        lease_token: str | None = None,
        generation: int | None = None,
        limit: int = 1,
    ) -> list[QmtCommand]:
        if type(limit) is not int:
            raise ValueError("limit must be an exact integer")
        if limit <= 0 or limit > self._max_poll_limit:
            raise ValueError(f"limit must be between 1 and {self._max_poll_limit}")
        now = self._clock()
        self._maintain(now)
        self._require_owner(owner_id, lease_token, generation)
        self.heartbeat(owner_id, lease_token, generation)
        assert self._owner is not None
        commands: list[QmtCommand] = []
        for _ in range(limit):
            if not self._pending:
                break
            command = self._pending.popleft()
            self._in_flight[command.command_id] = _InFlightCommand(
                command=command,
                claimed_at=now,
                owner_generation=self._owner.generation,
            )
            commands.append(command)
        return commands

    def post_result(
        self,
        owner_id: str,
        command_id: str,
        *,
        lease_token: str | None = None,
        generation: int | None = None,
        ok: bool,
        result: Any | None = None,
        error: dict[str, Any] | None = None,
    ) -> QmtCommandResult:
        now = self._clock()
        self._maintain(now)
        self._require_owner(owner_id, lease_token, generation)
        self.heartbeat(owner_id, lease_token, generation)
        assert self._owner is not None
        in_flight = self._in_flight.get(command_id)
        if in_flight is None or in_flight.owner_generation != self._owner.generation:
            raise QmtBridgeOwnershipError("QMT command is not owned by the active generation")
        self._in_flight.pop(command_id)
        command_result = QmtCommandResult(
            command_id=command_id,
            ok=ok,
            result=result,
            error=error,
            completed_at=now,
        )
        return self._store_result(command_result, method=in_flight.command.method)

    def expire_timed_out(self) -> list[str]:
        now = self._clock()
        self._prune_expired_results(now)
        return self._expire_timed_out(now)

    def _expire_timed_out(self, now: float) -> list[str]:
        expired: list[str] = []
        pending: deque[QmtCommand] = deque()
        for command in self._pending:
            if now - command.created_at <= command.timeout_seconds:
                pending.append(command)
                continue
            expired.append(command.command_id)
            self._record_timeout(command, now)
        self._pending = pending
        for command_id, in_flight in list(self._in_flight.items()):
            command = in_flight.command
            if now - in_flight.claimed_at <= command.timeout_seconds:
                continue
            expired.append(command_id)
            self._in_flight.pop(command_id, None)
            self._record_timeout(command, now)
        return expired

    def _record_timeout(self, command: QmtCommand, now: float) -> None:
        self._store_result(
            QmtCommandResult(
                command_id=command.command_id,
                ok=False,
                completed_at=now,
                error={
                    "code": "QMT_COMMAND_TIMEOUT",
                    "message": f"QMT command timed out: {_bounded_method(command.method)}",
                    "retryable": True,
                    "details": {"method": _bounded_method(command.method)},
                },
            ),
            method=command.method,
        )

    def result_for(self, command_id: str) -> QmtCommandResult | None:
        self._maintain(self._clock())
        stored = self._results.get(command_id)
        return stored.result if stored is not None else None

    def take_result(self, command_id: str) -> QmtCommandResult | None:
        """Return and remove a result consumed by an internal long-running client."""
        self._maintain(self._clock())
        stored = self._results.pop(command_id, None)
        if stored is None:
            return None
        self._retained_result_bytes -= stored.encoded_bytes
        return stored.result

    def command_state(self, command_id: str) -> str:
        self._maintain(self._clock())
        if command_id in self._results:
            return "completed"
        if command_id in self._in_flight:
            return "in_flight"
        if any(command.command_id == command_id for command in self._pending):
            return "pending"
        return "unknown"

    def raise_if_failed(self, command_id: str) -> None:
        result = self.result_for(command_id)
        if result is None or result.ok:
            return
        error = result.error or {}
        if error.get("code") == "QMT_COMMAND_TIMEOUT":
            raise QmtCommandTimeoutError(str(error.get("message", "QMT command timed out")))

    def health(self) -> dict[str, Any]:
        now = self._clock()
        self._maintain(now)
        owner_age = now - self._owner.last_heartbeat_at if self._owner else None
        owner_stale = self._owner_is_stale(now)
        oldest_pending_age = (
            max(now - command.created_at for command in self._pending)
            if self._pending
            else None
        )
        oldest_result_age = (
            max(now - stored.result.completed_at for stored in self._results.values())
            if self._results
            else None
        )
        return {
            "ownerId": self._owner.owner_id if self._owner else None,
            "lastHeartbeatAt": self._owner.last_heartbeat_at if self._owner else None,
            "ownerAgeSeconds": owner_age,
            "ownerStale": owner_stale,
            "ownerGeneration": self._owner.generation if self._owner else 0,
            "bridgeBuildId": self._owner.bridge_build_id if self._owner else None,
            "bridgeArtifactSha256": self._owner.bridge_artifact_sha256 if self._owner else None,
            "bridgeRuntimeFingerprint": (
                self._owner.bridge_runtime_fingerprint if self._owner else None
            ),
            "ready": self._owner is not None and not owner_stale,
            "pendingCount": len(self._pending),
            "inFlightCount": len(self._in_flight),
            "resultCount": len(self._results),
            "maxOutstandingCommands": self._max_outstanding_commands,
            "maxRetainedResults": self._max_retained_results,
            "resultTtlSeconds": self._result_ttl_seconds,
            "maxPollLimit": self._max_poll_limit,
            "maxCommandBytes": self._max_command_bytes,
            "maxResultBytes": self._max_result_bytes,
            "maxRetainedResultBytes": self._max_retained_result_bytes,
            "retainedResultBytes": self._retained_result_bytes,
            "oldestPendingAgeSeconds": oldest_pending_age,
            "oldestResultAgeSeconds": oldest_result_age,
            "commandRejectionTotals": [
                {"reason": reason, "value": self._rejection_totals[reason]}
                for reason in QMT_COMMAND_REJECTION_REASONS
            ],
        }

    def _owner_is_stale(self, now: float) -> bool:
        return bool(
            self._owner and now - self._owner.last_heartbeat_at > self._owner_stale_after_seconds
        )

    def _fail_commands_for_replaced_owner(self, now: float) -> None:
        commands = [*self._pending, *(item.command for item in self._in_flight.values())]
        self._pending.clear()
        self._in_flight.clear()
        for command in commands:
            self._store_result(
                QmtCommandResult(
                    command_id=command.command_id,
                    ok=False,
                    completed_at=now,
                    error={
                        "code": "QMT_BRIDGE_OWNER_REPLACED",
                        "message": (
                            "QMT command owner was replaced after its lease became stale"
                        ),
                        "retryable": True,
                        "details": {"method": _bounded_method(command.method)},
                    },
                ),
                method=command.method,
            )

    def _maintain(self, now: float) -> None:
        self._prune_expired_results(now)
        self._expire_timed_out(now)

    def _prune_expired_results(self, now: float) -> None:
        for command_id, stored in list(self._results.items()):
            if now <= stored.expires_at:
                continue
            self._results.pop(command_id, None)
            self._retained_result_bytes -= stored.encoded_bytes

    def _store_result(
        self,
        result: QmtCommandResult,
        *,
        method: str,
    ) -> QmtCommandResult:
        candidate = result
        reason: str | None = None
        try:
            encoded_bytes = _result_bytes(candidate)
        except (TypeError, ValueError):
            reason = "result_invalid"
            candidate = _failure_result(
                result.command_id,
                result.completed_at,
                code="QMT_COMMAND_RESULT_INVALID",
                message="QMT command result is not finite JSON",
                method=method,
            )
            encoded_bytes = _result_bytes(candidate)
        if reason is None and encoded_bytes > self._max_result_bytes:
            reason = "result_too_large"
            candidate = _failure_result(
                result.command_id,
                result.completed_at,
                code="QMT_COMMAND_RESULT_TOO_LARGE",
                message="QMT command result exceeds the per-result byte limit",
                method=method,
                extra={
                    "actualBytes": encoded_bytes,
                    "maxBytes": self._max_result_bytes,
                },
            )
            encoded_bytes = _result_bytes(candidate)
        outstanding_reservation = (
            self._outstanding_count() * TERMINAL_RESULT_RESERVATION_BYTES
        )
        if (
            self._retained_result_bytes
            + encoded_bytes
            + outstanding_reservation
            > self._max_retained_result_bytes
        ):
            reason = "result_capacity"
            candidate = _failure_result(
                result.command_id,
                result.completed_at,
                code="QMT_COMMAND_RESULT_CAPACITY_EXCEEDED",
                message="QMT command result exceeds retained-result capacity",
                method=method,
                extra=self._capacity_details(),
            )
            encoded_bytes = _result_bytes(candidate)
        if reason is not None and encoded_bytes > TERMINAL_RESULT_RESERVATION_BYTES:
            raise RuntimeError("bounded terminal failure exceeds reserved bytes")
        if reason is not None:
            self._rejection_totals[reason] += 1
        stored = _StoredResult(
            result=candidate,
            encoded_bytes=encoded_bytes,
            expires_at=result.completed_at + self._result_ttl_seconds,
        )
        previous = self._results.get(result.command_id)
        if previous is not None:
            self._retained_result_bytes -= previous.encoded_bytes
        self._results[result.command_id] = stored
        self._retained_result_bytes += encoded_bytes
        return candidate

    def _outstanding_count(self) -> int:
        return len(self._pending) + len(self._in_flight)

    def _capacity_details(self) -> dict[str, Any]:
        return {
            "pendingCount": len(self._pending),
            "inFlightCount": len(self._in_flight),
            "resultCount": len(self._results),
            "maxOutstandingCommands": self._max_outstanding_commands,
            "maxRetainedResults": self._max_retained_results,
            "retainedResultBytes": self._retained_result_bytes,
            "maxRetainedResultBytes": self._max_retained_result_bytes,
        }

    def _reject(
        self,
        *,
        reason: str,
        code: str,
        message: str,
        http_status: int,
        details: dict[str, Any],
    ) -> None:
        self._rejection_totals[reason] += 1
        raise QmtCommandRejectedError(
            code=code,
            message=message,
            http_status=http_status,
            retryable=reason == "capacity",
            details=details,
        )

    def _require_owner(
        self,
        owner_id: str,
        lease_token: str | None = None,
        generation: int | None = None,
    ) -> None:
        if self._owner is None:
            raise QmtBridgeOwnershipError("QMT bridge owner is not registered")
        if self._owner.owner_id != owner_id:
            raise QmtBridgeOwnershipError(
                f"QMT bridge owner mismatch: expected {self._owner.owner_id}, got {owner_id}"
            )
        if lease_token is not None and not secrets.compare_digest(
            self._owner.lease_token, lease_token
        ):
            raise QmtBridgeOwnershipError("QMT bridge lease token mismatch")
        if generation is not None and self._owner.generation != generation:
            raise QmtBridgeOwnershipError("QMT bridge generation mismatch")


def _monotonic_seconds() -> float:
    import time

    return time.monotonic()


def _positive_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be an exact positive integer")
    return value


def _positive_finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a positive finite number")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return normalized


def _json_bytes(value: Any) -> int:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return len(encoded)


def _result_bytes(result: QmtCommandResult) -> int:
    return _json_bytes(
        {
            "commandId": result.command_id,
            "ok": result.ok,
            "completedAt": result.completed_at,
            "result": result.result,
            "error": result.error,
        }
    )


def _bounded_method(method: Any) -> str:
    return str(method)[:128]


def _failure_result(
    command_id: str,
    completed_at: float,
    *,
    code: str,
    message: str,
    method: str,
    extra: dict[str, Any] | None = None,
) -> QmtCommandResult:
    details = {"method": _bounded_method(method)}
    if extra:
        details.update(extra)
    return QmtCommandResult(
        command_id=command_id,
        ok=False,
        completed_at=completed_at,
        error={
            "code": code,
            "message": message,
            "retryable": True,
            "details": details,
        },
    )
