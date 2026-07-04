from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


class QmtBridgeOwnershipError(Exception):
    """Raised when a non-owner bridge attempts to process QMT commands."""


class QmtCommandTimeoutError(Exception):
    """Raised when a QMT command has already timed out."""


@dataclass(frozen=True)
class QmtBridgeOwner:
    owner_id: str
    registered_at: float
    last_heartbeat_at: float


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


class QmtCommandGateway:
    """In-memory command gateway for the single-owner full-QMT bridge."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        default_timeout_seconds: float = 10.0,
    ) -> None:
        self._clock = clock or _monotonic_seconds
        self._default_timeout_seconds = default_timeout_seconds
        self._owner: QmtBridgeOwner | None = None
        self._pending: deque[QmtCommand] = deque()
        self._in_flight: dict[str, _InFlightCommand] = {}
        self._results: dict[str, QmtCommandResult] = {}

    def register_owner(self, owner_id: str) -> QmtBridgeOwner:
        now = self._clock()
        if self._owner is not None and self._owner.owner_id != owner_id:
            raise QmtBridgeOwnershipError(
                f"QMT bridge owner already registered: {self._owner.owner_id}"
            )
        self._owner = QmtBridgeOwner(
            owner_id=owner_id,
            registered_at=self._owner.registered_at if self._owner else now,
            last_heartbeat_at=now,
        )
        return self._owner

    def heartbeat(self, owner_id: str) -> QmtBridgeOwner:
        self._require_owner(owner_id)
        assert self._owner is not None
        self._owner = QmtBridgeOwner(
            owner_id=self._owner.owner_id,
            registered_at=self._owner.registered_at,
            last_heartbeat_at=self._clock(),
        )
        return self._owner

    def enqueue(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_seconds: float | None = None,
    ) -> QmtCommand:
        command = QmtCommand(
            command_id=str(uuid4()),
            method=method,
            params=dict(params),
            created_at=self._clock(),
            timeout_seconds=timeout_seconds or self._default_timeout_seconds,
        )
        self._pending.append(command)
        return command

    def poll(self, owner_id: str, *, limit: int = 1) -> list[QmtCommand]:
        self._require_owner(owner_id)
        self.heartbeat(owner_id)
        commands: list[QmtCommand] = []
        now = self._clock()
        for _ in range(max(limit, 0)):
            if not self._pending:
                break
            command = self._pending.popleft()
            self._in_flight[command.command_id] = _InFlightCommand(
                command=command,
                claimed_at=now,
            )
            commands.append(command)
        return commands

    def post_result(
        self,
        owner_id: str,
        command_id: str,
        *,
        ok: bool,
        result: Any | None = None,
        error: dict[str, Any] | None = None,
    ) -> QmtCommandResult:
        self._require_owner(owner_id)
        self.heartbeat(owner_id)
        self._in_flight.pop(command_id, None)
        command_result = QmtCommandResult(
            command_id=command_id,
            ok=ok,
            result=result,
            error=error,
            completed_at=self._clock(),
        )
        self._results[command_id] = command_result
        return command_result

    def expire_timed_out(self) -> list[str]:
        now = self._clock()
        expired: list[str] = []
        for command_id, in_flight in list(self._in_flight.items()):
            command = in_flight.command
            if now - in_flight.claimed_at <= command.timeout_seconds:
                continue
            expired.append(command_id)
            self._in_flight.pop(command_id, None)
            self._results[command_id] = QmtCommandResult(
                command_id=command_id,
                ok=False,
                completed_at=now,
                error={
                    "code": "QMT_COMMAND_TIMEOUT",
                    "message": f"QMT command timed out: {command.method}",
                    "retryable": True,
                    "details": {"method": command.method},
                },
            )
        return expired

    def result_for(self, command_id: str) -> QmtCommandResult | None:
        return self._results.get(command_id)

    def raise_if_failed(self, command_id: str) -> None:
        result = self.result_for(command_id)
        if result is None or result.ok:
            return
        error = result.error or {}
        if error.get("code") == "QMT_COMMAND_TIMEOUT":
            raise QmtCommandTimeoutError(str(error.get("message", "QMT command timed out")))

    def health(self) -> dict[str, Any]:
        return {
            "ownerId": self._owner.owner_id if self._owner else None,
            "lastHeartbeatAt": self._owner.last_heartbeat_at if self._owner else None,
            "pendingCount": len(self._pending),
            "inFlightCount": len(self._in_flight),
            "resultCount": len(self._results),
        }

    def _require_owner(self, owner_id: str) -> None:
        if self._owner is None:
            raise QmtBridgeOwnershipError("QMT bridge owner is not registered")
        if self._owner.owner_id != owner_id:
            raise QmtBridgeOwnershipError(
                f"QMT bridge owner mismatch: expected {self._owner.owner_id}, got {owner_id}"
            )


def _monotonic_seconds() -> float:
    import time

    return time.monotonic()
