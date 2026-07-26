import secrets
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


class QmtCommandGateway:
    """In-memory command gateway for the single-owner full-QMT bridge."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        default_timeout_seconds: float = 10.0,
        owner_stale_after_seconds: float = 15.0,
    ) -> None:
        self._clock = clock or _monotonic_seconds
        self._default_timeout_seconds = default_timeout_seconds
        self._owner_stale_after_seconds = owner_stale_after_seconds
        self._owner: QmtBridgeOwner | None = None
        self._pending: deque[QmtCommand] = deque()
        self._in_flight: dict[str, _InFlightCommand] = {}
        self._results: dict[str, QmtCommandResult] = {}

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
        command = QmtCommand(
            command_id=str(uuid4()),
            method=method,
            params=dict(params),
            created_at=self._clock(),
            timeout_seconds=timeout_seconds or self._default_timeout_seconds,
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
        self._require_owner(owner_id, lease_token, generation)
        self.heartbeat(owner_id, lease_token, generation)
        assert self._owner is not None
        commands: list[QmtCommand] = []
        now = self._clock()
        for _ in range(max(limit, 0)):
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
            completed_at=self._clock(),
        )
        self._results[command_id] = command_result
        return command_result

    def expire_timed_out(self) -> list[str]:
        now = self._clock()
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
        self._results[command.command_id] = QmtCommandResult(
            command_id=command.command_id,
            ok=False,
            completed_at=now,
            error={
                "code": "QMT_COMMAND_TIMEOUT",
                "message": f"QMT command timed out: {command.method}",
                "retryable": True,
                "details": {"method": command.method},
            },
        )

    def result_for(self, command_id: str) -> QmtCommandResult | None:
        return self._results.get(command_id)

    def take_result(self, command_id: str) -> QmtCommandResult | None:
        """Return and remove a result consumed by an internal long-running client."""
        return self._results.pop(command_id, None)

    def raise_if_failed(self, command_id: str) -> None:
        result = self.result_for(command_id)
        if result is None or result.ok:
            return
        error = result.error or {}
        if error.get("code") == "QMT_COMMAND_TIMEOUT":
            raise QmtCommandTimeoutError(str(error.get("message", "QMT command timed out")))

    def health(self) -> dict[str, Any]:
        now = self._clock()
        owner_age = now - self._owner.last_heartbeat_at if self._owner else None
        owner_stale = self._owner_is_stale(now)
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
            self._results[command.command_id] = QmtCommandResult(
                command_id=command.command_id,
                ok=False,
                completed_at=now,
                error={
                    "code": "QMT_BRIDGE_OWNER_REPLACED",
                    "message": "QMT command owner was replaced after its lease became stale",
                    "retryable": True,
                    "details": {"method": command.method},
                },
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
