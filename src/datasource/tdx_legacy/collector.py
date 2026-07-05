"""Snapshot collector driven by TDX subscription callbacks."""

import asyncio
import contextlib
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from src.core.config import settings
from src.datasource.tdx_legacy.bridge import TdxLegacyBridge
from src.datasource.tdx_models import TdxSnapshot
from src.datasource.tdx_normalization import normalize_symbol


class TdxLegacyMinuteCollector:
    """Collect latest snapshots for symbols marked dirty by quote callbacks."""

    def __init__(
        self,
        *,
        provider: Any,
        bridge: TdxLegacyBridge,
        period: str,
        collect_delay_seconds: float | None = None,
        retry_delay_seconds: float | None = None,
        snapshot_publisher: Callable[[TdxSnapshot], Awaitable[None]] | None = None,
    ) -> None:
        self.provider = provider
        self.bridge = bridge
        self.period = period
        self.collect_delay_seconds = (
            float(settings.tdx.collect_delay_seconds)
            if collect_delay_seconds is None
            else collect_delay_seconds
        )
        self.retry_delay_seconds = (
            float(settings.tdx.retry_delay_seconds)
            if retry_delay_seconds is None
            else retry_delay_seconds
        )
        self.dirty_symbols: set[str] = set()
        self.stale_symbols: set[str] = set()
        self.last_error_code: str | None = None
        self.last_error: str | None = None
        self.state = "not_started"
        self.snapshot_publisher = snapshot_publisher
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def last_minute_bar_at(self) -> str | None:
        return self.bridge.last_minute_bar_at

    @property
    def event_queue_depth(self) -> int:
        return self.bridge.event_queue_depth

    @property
    def event_queue_capacity(self) -> int:
        return self.bridge.event_queue_capacity

    def mark_dirty(self, symbol: str) -> None:
        self.dirty_symbols.add(normalize_symbol(symbol))

    def mark_dirty_from_callback(self, payload: dict[str, Any]) -> None:
        code = payload.get("Code")
        if isinstance(code, str) and code:
            loop = self._loop
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(self.mark_dirty, code)
            else:
                self.mark_dirty(code)

    async def collect_dirty_once(self) -> int:
        symbols = sorted(self.dirty_symbols)
        if not symbols:
            return 0
        symbols = self._filter_active_dirty_symbols(symbols)
        if not symbols:
            return 0

        self.dirty_symbols.difference_update(symbols)
        try:
            raw_snapshots = await self.provider.get_snapshots(symbols)
        except Exception as exc:
            self.dirty_symbols.update(symbols)
            self.stale_symbols.update(symbols)
            self.state = "error"
            self.last_error_code = "TDX_COLLECTOR_SNAPSHOT_ERROR"
            self.last_error = str(exc)
            self.bridge.last_error_code = self.last_error_code
            return 0

        snapshots = [_coerce_snapshot(raw_snapshot) for raw_snapshot in raw_snapshots]
        emitted = 0
        fresh_symbols: set[str] = set()
        symbols_with_snapshots = {snapshot.symbol for snapshot in snapshots}
        publish_errors: list[str] = []
        for snapshot in snapshots:
            self.bridge.record_callback()
            fresh_symbols.add(snapshot.symbol)
            emitted += 1
            if self.snapshot_publisher is not None:
                try:
                    await self.snapshot_publisher(snapshot)
                except Exception as exc:
                    publish_errors.append(str(exc))

        stale_symbols = set(symbols) - symbols_with_snapshots
        self.stale_symbols.difference_update(fresh_symbols)
        if publish_errors:
            self.state = "error"
            self.last_error_code = "TDX_COLLECTOR_PUBLISH_ERROR"
            self.last_error = "; ".join(publish_errors)
            self.bridge.last_error_code = self.last_error_code
        elif stale_symbols:
            self.stale_symbols.update(stale_symbols)
            self.state = "stale"
            self.last_error_code = "TDX_COLLECTOR_STALE"
            self.last_error = "No fresh snapshots returned for dirty symbols"
            self.bridge.last_error_code = self.last_error_code
        else:
            if emitted > 0 or self.last_error_code != "TDX_COLLECTOR_PUBLISH_ERROR":
                self.state = "running" if self._task and not self._task.done() else "idle"
                self.last_error_code = None
                self.last_error = None

        return emitted

    def _filter_active_dirty_symbols(self, symbols: list[str]) -> list[str]:
        if not getattr(self.bridge, "subscription_state_known", False):
            return symbols

        active = set(self.bridge.active_subscriptions)
        active_symbols = [symbol for symbol in symbols if symbol in active]
        inactive_symbols = set(symbols) - set(active_symbols)
        self.dirty_symbols.difference_update(inactive_symbols)
        return active_symbols

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._loop = asyncio.get_running_loop()
        self._stopping = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stopping.set()
        task = self._task
        if task is None:
            self._loop = None
            self.state = "stopped"
            return
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        self._loop = None
        self.state = "stopped"

    async def _run_loop(self) -> None:
        try:
            while not self._stopping.is_set():
                await self.collect_dirty_once()
                delay = (
                    self.retry_delay_seconds
                    if self.state == "error"
                    else self.collect_delay_seconds
                )
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            raise


def _coerce_snapshot(raw_snapshot: TdxSnapshot | dict[str, Any]) -> TdxSnapshot:
    snapshot = (
        raw_snapshot
        if isinstance(raw_snapshot, TdxSnapshot)
        else TdxSnapshot.model_validate(raw_snapshot)
    )
    normalized_symbol = normalize_symbol(snapshot.symbol)
    if normalized_symbol == snapshot.symbol:
        return snapshot
    return snapshot.model_copy(update={"symbol": normalized_symbol})


def dirty_symbols_from_payloads(payloads: Iterable[dict[str, Any]]) -> set[str]:
    symbols: set[str] = set()
    for payload in payloads:
        code = payload.get("Code")
        if isinstance(code, str) and code:
            symbols.add(normalize_symbol(code))
    return symbols
