"""Subscription recovery state machine (shared by TDX and QMT).

Pure logic, no I/O: hosts feed activity events (``observe_snapshot`` /
``observe_callback``), a watchdog ticks ``evaluate()``, and the host reads
``push_state`` to choose poll/sync semantics.

States (decision 2026-08-20, spec realtime-subscription-restart-recovery):

- IDLE      — outside the A-share activity window (default
              ``09:15-11:30,13:00-15:00`` UTC+8): zero resubscribe, zero
              detection, zero alarm.
- PUSHING   — in window and no data flowing: host performs full resubscribe
              until a snapshot arrives.
- VERIFIED  — in window and data flowing: host stops (zero extra SDK calls).
- escalated — PUSHING has performed ``max_recovery_cycles`` rounds without any
              activity (alarm; never auto-restart processes).

The window is the single time boundary (config ``MIST_ACTIVITY_WINDOWS``,
compose-single-source); hosts never do their own session inference.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from typing import Literal

PushState = Literal["idle", "pushing", "verified"]

_DEFAULT_WINDOW = "09:15-11:30,13:00-15:00"
_UTC8 = timezone(timedelta(hours=8))


def _parse_hhmm(value: str) -> dtime:
    hour_s, _, minute_s = value.partition(":")
    return dtime(hour=int(hour_s), minute=int(minute_s or "0"))


class ActivityWindow:
    """A-share intraday activity window (UTC+8, multi-segment across lunch).

    ``MIST_ACTIVITY_WINDOWS`` format: ``HH:MM-HH:MM,HH:MM-HH:MM`` (default
    ``09:15-11:30,13:00-15:00``, 09:15 auction start, lunch excluded).
    """

    def __init__(
        self,
        env_value: str | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._now = now or (lambda: datetime.now(_UTC8))
        self._segments = self._parse(env_value or os.environ.get("MIST_ACTIVITY_WINDOWS", _DEFAULT_WINDOW))

    @staticmethod
    def _parse(value: str) -> list[tuple[dtime, dtime]]:
        segments: list[tuple[dtime, dtime]] = []
        for part in value.split(","):
            start_s, _, end_s = part.partition("-")
            segments.append((_parse_hhmm(start_s), _parse_hhmm(end_s)))
        return segments

    def in_window(self, now: datetime | None = None) -> bool:
        current = (now or self._now()).time()
        return any(start <= current < end for start, end in self._segments)


class StallDetector:
    """Three-state subscription recovery state machine (pure, fake-clockable).

    Thresholds are constructor-injected (env-sourced by the host or defaults
    here) so unit tests can drive every transition with a fake monotonic clock.
    """

    def __init__(
        self,
        *,
        source: str,
        window: ActivityWindow | None = None,
        stall_grace_seconds: float = 180.0,
        max_recovery_cycles: int = 3,
        now: Callable[[], float] | None = None,
        on_change: Callable[[PushState], None] | None = None,
    ) -> None:
        self.source = source
        self._window = window or ActivityWindow()
        self._grace = stall_grace_seconds
        self._max_cycles = max_recovery_cycles
        self._now = now or time.monotonic
        self._on_change = on_change
        self._last_activity: float | None = None
        self._cycle_count = 0
        self._state: PushState = "idle"
        self._escalated = False

    # -- host feeding ---------------------------------------------------

    def observe_snapshot(self) -> None:
        """A snapshot was accepted — data is flowing."""
        self._touch()

    def observe_callback(self) -> None:
        """Bridge callback counters advanced — auxiliary activity signal."""
        self._touch()

    def _touch(self) -> None:
        self._last_activity = self._now()
        self._cycle_count = 0
        self._escalated = False
        if self._window.in_window():
            self._set("verified")

    # -- recovery action bookkeeping ------------------------------------

    def note_recovery(self) -> None:
        """Host calls once per resubscribe / force-sync performed in PUSHING."""
        if self._state == "pushing":
            self._cycle_count += 1

    # -- tick ------------------------------------------------------------

    def evaluate(self) -> None:
        """Advance the state machine. Watchdog calls every tick (default 5s)."""
        if not self._window.in_window():
            self._set("idle")
            self._cycle_count = 0
            return
        if self._last_activity is None:
            # In window with no historical activity: initial resubscribe until
            # a snapshot flows (also catches pre-open stalls from window start).
            self._set("pushing")
            return
        ago = self._now() - self._last_activity
        if ago <= self._grace:
            self._set("verified")
        else:
            self._set("pushing")
            if self._cycle_count >= self._max_cycles:
                self._escalated = True

    def _set(self, state: PushState) -> None:
        if state == self._state:
            return
        self._state = state
        if self._on_change is not None:
            self._on_change(state)

    # -- host queries ----------------------------------------------------

    @property
    def push_state(self) -> PushState:
        return self._state

    @property
    def stall_detected(self) -> bool:
        return self._state == "pushing"

    @property
    def stall_escalated(self) -> bool:
        return self._escalated

    @property
    def in_window(self) -> bool:
        return self._window.in_window()

    @property
    def grace_seconds(self) -> float:
        return self._grace

    @property
    def max_recovery_cycles(self) -> int:
        return self._max_cycles

    @property
    def recovery_cycles_done(self) -> int:
        return self._cycle_count
