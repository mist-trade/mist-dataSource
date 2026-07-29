"""Process-local QMT realtime connection and readiness state."""

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from src.datasource.qmt.realtime.gateway import QmtCommandGateway


class QmtRealtimeCollector:
    """Retained runtime-store name for the callback-driven QMT transport.

    Native acquisition is performed by subscription callbacks in the embedded
    bridge. This object never schedules ``get_full_tick`` or another market-data
    polling command.
    """

    def __init__(
        self,
        *,
        gateway: QmtCommandGateway,
        publisher: Callable[[dict[str, Any]], Awaitable[None] | None],
        error_publisher: Callable[[str, str], Awaitable[None] | None] | None = None,
        now: Callable[[], datetime] | None = None,
        interval_seconds: float = 1.0,
    ) -> None:
        self.gateway = gateway
        self.publisher = publisher
        self.error_publisher = error_publisher
        self.connected_clients: set[str] = set()
        self.leader_client_id: str | None = None
        self.state = "not_started"
        self.last_quote_at: str | None = None
        self.last_error_code: str | None = None
        self.last_error: str | None = None
        self._now = now or (lambda: datetime.now(UTC))
        _ = interval_seconds

    def claim_leader(self, client_id: str) -> bool:
        self.connected_clients.add(client_id)
        if self.leader_client_id in (None, client_id):
            self.leader_client_id = client_id
            return True
        return False

    def disconnect(self, client_id: str) -> None:
        self.connected_clients.discard(client_id)
        if self.leader_client_id == client_id:
            self.leader_client_id = None

    async def start(self) -> None:
        self.state = "ready"

    async def stop(self) -> None:
        self.state = "stopped"

    def record_snapshot(self, captured_at: str) -> None:
        self.state = "running"
        self.last_quote_at = captured_at
        self.last_error_code = None
        self.last_error = None

    def record_error(self, code: str, message: str) -> None:
        self.state = "error"
        self.last_error_code = code
        self.last_error = message

    def health(self) -> dict[str, Any]:
        bridge = self.gateway.health()
        snapshot_age: float | None = None
        if self.last_quote_at is not None:
            try:
                captured = datetime.fromisoformat(
                    self.last_quote_at.replace("Z", "+00:00")
                )
                if captured.tzinfo is not None:
                    snapshot_age = max(
                        0.0,
                        (self._now().astimezone(UTC) - captured.astimezone(UTC)).total_seconds(),
                    )
            except ValueError:
                snapshot_age = None
        return {
            "mode": "builtin",
            "schemaVersion": 2,
            "source": "qmt",
            "quality": "latest-state",
            "state": self.state,
            "connectionCount": len(self.connected_clients),
            "leaderClientId": self.leader_client_id,
            "lastQuoteAt": self.last_quote_at,
            "lastSnapshotAgeSeconds": snapshot_age,
            "lastErrorCode": self.last_error_code,
            "lastError": self.last_error,
            "bridge": bridge,
        }

    def ready_contract(self) -> dict[str, Any]:
        return {
            "mode": "builtin",
            "schemaVersion": 2,
            "source": "QMT",
            "quality": "latest-state",
        }
