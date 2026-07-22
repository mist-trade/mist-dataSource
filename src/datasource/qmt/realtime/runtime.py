import asyncio
import contextlib
import inspect
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from src.datasource.qmt.bridge import QmtCommandGateway
from src.datasource.qmt.realtime.contract import (
    BEIJING_TZ,
    QMT_REALTIME_ACQUISITION_PROFILE,
    QMT_REALTIME_MAX_SUBSCRIPTIONS,
    QMT_REALTIME_PAYLOAD_TYPE,
    QMT_REALTIME_SCHEMA_VERSION,
    QMT_SYMBOL_PATTERN,
    as_beijing,
    is_realtime_trading_session,
    is_valid_snapshot,
)
from src.datasource.realtime_native_safety import (
    NativePayloadSafetyError,
    validate_native_payload_safety,
)


class QmtRealtimeCollector:
    """Poll native QMT snapshots through the single-owner command gateway."""

    def __init__(
        self,
        *,
        gateway: QmtCommandGateway,
        publisher: Callable[[dict[str, Any]], Awaitable[None] | None],
        epoch_publisher: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
        error_publisher: Callable[[str, str], Awaitable[None] | None] | None = None,
        now: Callable[[], datetime] | None = None,
        interval_seconds: float = 1.0,
    ) -> None:
        self.gateway = gateway
        self.publisher = publisher
        self.epoch_publisher = epoch_publisher
        self.error_publisher = error_publisher
        self._now = now or (lambda: datetime.now(BEIJING_TZ))
        self.interval_seconds = interval_seconds
        self.active_subscriptions: list[str] = []
        self.connected_clients: set[str] = set()
        self.leader_client_id: str | None = None
        self._command_id: str | None = None
        self._command_symbols: list[str] = []
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self.state = "not_started"
        self.skipped_overlap_count = 0
        self.last_command_at: str | None = None
        self.last_quote_at: str | None = None
        self.last_error_code: str | None = None
        self.last_error: str | None = None
        self.stream_epoch = str(uuid4())
        self.sequences: dict[str, int] = {}
        self._owner_generation = 0

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
            self.active_subscriptions = []

    def sync_subscriptions(self, symbols: Iterable[str]) -> list[str]:
        accepted, _ = self.partition_symbols(symbols)
        self.active_subscriptions = accepted
        return list(self.active_subscriptions)

    def partition_symbols(self, symbols: Iterable[str]) -> tuple[list[str], list[dict[str, Any]]]:
        accepted: list[str] = []
        rejected: list[dict[str, Any]] = []
        for raw_symbol in symbols:
            symbol = str(raw_symbol).strip().upper()
            if symbol in accepted:
                continue
            if not QMT_SYMBOL_PATTERN.fullmatch(symbol):
                rejected.append(
                    {
                        "symbol": symbol,
                        "code": "QMT_REALTIME_SYMBOL_INVALID",
                        "reason": "symbol must use an exact QMT market suffix",
                    }
                )
                continue
            if len(accepted) >= QMT_REALTIME_MAX_SUBSCRIPTIONS:
                rejected.append(
                    {
                        "symbol": symbol,
                        "code": "QMT_REALTIME_ALLOWLIST_LIMIT",
                        "reason": "at most five realtime symbols are allowed",
                    }
                )
                continue
            accepted.append(symbol)
        return sorted(accepted), rejected

    def subscribe(self, symbols: Iterable[str]) -> list[str]:
        return self.sync_subscriptions([*self.active_subscriptions, *symbols])

    def unsubscribe(self, symbols: Iterable[str]) -> list[str]:
        removed = {str(symbol).strip().upper() for symbol in symbols}
        return self.sync_subscriptions(
            symbol for symbol in self.active_subscriptions if symbol not in removed
        )

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping.clear()
        self._rotate_epoch()
        self.state = "idle"
        self._task = asyncio.create_task(self._run(), name="qmt-realtime-collector")

    async def stop(self) -> None:
        self._stopping.set()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self.state = "stopped"

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                await self.collect_once()
            except Exception as exc:
                self._set_error("QMT_REALTIME_COLLECTOR_ERROR", str(exc))
            await asyncio.sleep(self.interval_seconds)

    async def collect_once(self) -> int:
        symbols = list(self.active_subscriptions)
        now = as_beijing(self._now())
        bridge = self.gateway.health()
        await self._sync_owner_epoch(
            int(bridge["ownerGeneration"]),
            str(bridge["ownerId"]) if bridge["ownerId"] is not None else None,
        )

        if self._command_id is not None:
            self.gateway.expire_timed_out()
            result = self.gateway.take_result(self._command_id)
            if result is None:
                self.skipped_overlap_count += 1
                self.state = "waiting"
                return 0
            command_symbols = list(self._command_symbols)
            self._command_id = None
            self._command_symbols = []
            if not result.ok:
                error = result.error or {}
                self._set_error(
                    str(error.get("code", "QMT_REALTIME_COMMAND_FAILED")),
                    str(error.get("message", "QMT realtime command failed")),
                )
                return 0
            emitted = await self._publish_result(result.result, now, command_symbols)
            if not symbols:
                self.state = "idle"
                return emitted
            if not is_realtime_trading_session(now, symbols):
                self.state = "outside_session"
                return emitted
            if not self.gateway.health()["ready"]:
                self._set_error("QMT_BRIDGE_OWNER_MISSING", "QMT bridge owner is not ready")
                return emitted
            self._enqueue_command(symbols, now, clear_error=emitted > 0)
            return emitted

        if not symbols:
            self.state = "idle"
            return 0

        if not is_realtime_trading_session(now, symbols):
            self.state = "outside_session"
            return 0

        if not bridge["ready"]:
            self._set_error("QMT_BRIDGE_OWNER_MISSING", "QMT bridge owner is not ready")
            return 0

        self._enqueue_command(symbols, now, clear_error=True)
        return 0

    def _enqueue_command(
        self,
        symbols: list[str],
        now: datetime,
        *,
        clear_error: bool,
    ) -> None:
        command = self.gateway.enqueue("get_full_tick", {"symbols": symbols})
        self._command_id = command.command_id
        self._command_symbols = list(symbols)
        self.last_command_at = now.isoformat()
        if clear_error:
            self.last_error_code = None
            self.last_error = None
        self.state = "waiting"

    async def _publish_result(
        self,
        payload: Any,
        now: datetime,
        command_symbols: list[str],
    ) -> int:
        if not isinstance(payload, dict):
            self._set_error("QMT_REALTIME_INVALID_PAYLOAD", "QMT result must be a mapping")
            return 0
        payload_map = cast(dict[str, Any], payload)

        emitted = 0
        active = set(self.active_subscriptions)
        for symbol in command_symbols:
            if symbol not in active:
                continue
            snapshot = payload_map.get(symbol)
            if not is_valid_snapshot(snapshot, now):
                self._set_error(
                    "QMT_REALTIME_INVALID_PAYLOAD",
                    f"Invalid QMT realtime payload for {symbol}",
                )
                continue
            try:
                validate_native_payload_safety(cast(dict[str, Any], snapshot))
            except NativePayloadSafetyError as exc:
                self._set_error("QMT_REALTIME_UNSAFE_NATIVE", str(exc))
                continue
            sequence = self.sequences.get(symbol, 0) + 1
            self.sequences[symbol] = sequence
            value = self.publisher(
                {
                    "payloadType": QMT_REALTIME_PAYLOAD_TYPE,
                    "schemaVersion": QMT_REALTIME_SCHEMA_VERSION,
                    "source": "qmt",
                    "acquisitionProfile": QMT_REALTIME_ACQUISITION_PROFILE,
                    "streamEpoch": self.stream_epoch,
                    "sequence": sequence,
                    "sequenceScope": "symbol",
                    "symbol": symbol,
                    "capturedAt": now.isoformat(),
                    "native": snapshot,
                }
            )
            if inspect.isawaitable(value):
                await value
            emitted += 1

        if emitted:
            self.state = "running"
            self.last_quote_at = now.isoformat()
            self.last_error_code = None
            self.last_error = None
        return emitted

    def _set_error(self, code: str, message: str) -> None:
        self.state = "error"
        self.last_error_code = code
        self.last_error = message
        if self.error_publisher is not None:
            value = self.error_publisher(code, message)
            if inspect.isawaitable(value):
                asyncio.get_running_loop().create_task(self._await_publisher(value))

    async def _await_publisher(self, value: Awaitable[None]) -> None:
        await value

    def health(self) -> dict[str, Any]:
        return {
            "payloadType": QMT_REALTIME_PAYLOAD_TYPE,
            "mode": "builtin",
            "schemaVersion": QMT_REALTIME_SCHEMA_VERSION,
            "source": "qmt",
            "sequenceScope": "symbol",
            "acquisitionProfile": QMT_REALTIME_ACQUISITION_PROFILE,
            "streamEpoch": self.stream_epoch,
            "sequences": dict(self.sequences),
            "state": self.state,
            "connectionCount": len(self.connected_clients),
            "leaderClientId": self.leader_client_id,
            "activeSubscriptions": list(self.active_subscriptions),
            "inFlight": self._command_id is not None,
            "skippedOverlapCount": self.skipped_overlap_count,
            "lastCommandAt": self.last_command_at,
            "lastQuoteAt": self.last_quote_at,
            "lastErrorCode": self.last_error_code,
            "lastError": self.last_error,
            "bridge": self.gateway.health(),
        }

    def ready_contract(self) -> dict[str, Any]:
        return {
            "payloadType": QMT_REALTIME_PAYLOAD_TYPE,
            "mode": "builtin",
            "schemaVersion": QMT_REALTIME_SCHEMA_VERSION,
            "source": "qmt",
            "sequenceScope": "symbol",
            "acquisitionProfile": QMT_REALTIME_ACQUISITION_PROFILE,
            "streamEpoch": self.stream_epoch,
            "sequence": 0,
        }

    async def _sync_owner_epoch(self, owner_generation: int, owner_id: str | None) -> None:
        if owner_generation == self._owner_generation:
            return
        self._owner_generation = owner_generation
        self._rotate_epoch()
        if self.epoch_publisher is not None:
            value = self.epoch_publisher(
                {
                    **self.ready_contract(),
                    "generation": owner_generation,
                    "ownerId": owner_id,
                }
            )
            if inspect.isawaitable(value):
                await value

    def _rotate_epoch(self) -> None:
        self.stream_epoch = str(uuid4())
        self.sequences.clear()
