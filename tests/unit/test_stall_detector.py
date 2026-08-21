"""Unit tests for the shared StallDetector / ActivityWindow state machine.

Fake monotonic clock drives every transition deterministically (no I/O).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.datasource.realtime.stall_detector import ActivityWindow, StallDetector

_UTC8 = timezone(timedelta(hours=8))


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 20, hour, minute, tzinfo=_UTC8)


def _make_fakes(start_sec: float = 1000.0):
    """Return (detector factory, clock-stepper holding the fake monotonic)."""
    state = {"t": start_sec}

    def now() -> float:
        return state["t"]

    def window_at(dt: datetime) -> ActivityWindow:
        return ActivityWindow(env_value="09:15-11:30,13:00-15:00", now=lambda: dt)

    def make_detector() -> StallDetector:
        # window with a live now is replaced in tests that need in_window;
        # default uses a long-lived in-window datetime for focus on transitions.
        dt = _at(10, 0)
        return StallDetector(
            source="tdx",
            window=window_at(dt),
            stall_grace_seconds=180.0,
            max_recovery_cycles=3,
            now=now,
        )

    def advance(seconds: float) -> None:
        state["t"] += seconds

    return make_detector, advance, now


def test_activity_window_parse_and_boundaries() -> None:
    w = ActivityWindow(env_value="09:15-11:30,13:00-15:00", now=lambda: _at(10, 0))
    assert w.in_window(_at(10, 0)) is True
    assert w.in_window(_at(9, 14)) is False
    assert w.in_window(_at(9, 15)) is True
    assert w.in_window(_at(11, 29)) is True
    assert w.in_window(_at(11, 30)) is False  # lunch start excluded
    assert w.in_window(_at(13, 0)) is True
    assert w.in_window(_at(15, 0)) is False  # window end excluded
    assert w.in_window(_at(23, 59)) is False


def test_outside_window_is_idle_and_resets() -> None:
    make, advance, _ = _make_fakes()
    d = make()
    d.observe_snapshot()
    # Force the detector's window to be outside by re-checking: simulate by a
    # detector whose window is a night datetime.
    night = StallDetector(
        source="tdx",
        window=ActivityWindow(env_value="09:15-11:30,13:00-15:00", now=lambda: _at(2, 0)),
        stall_grace_seconds=180.0,
        max_recovery_cycles=3,
        now=lambda: 1000.0,
    )
    night.evaluate()
    assert night.push_state == "idle"
    assert night.stall_detected is False
    assert night.stall_escalated is False


def test_in_window_no_activity_is_pushing() -> None:
    make, _, _ = _make_fakes()
    d = make()
    d.evaluate()
    assert d.push_state == "pushing"


def test_snapshot_reaches_verified() -> None:
    make, advance, _ = _make_fakes()
    d = make()
    d.observe_snapshot()
    assert d.push_state == "verified"


def test_silence_over_grace_returns_to_pushing() -> None:
    make, advance, _ = _make_fakes()
    d = make()
    d.observe_snapshot()
    assert d.push_state == "verified"
    advance(181)
    d.evaluate()
    assert d.push_state == "pushing"
    assert d.stall_detected is True


def test_activity_recovers_and_clears_escalated() -> None:
    make, advance, _ = _make_fakes()
    d = make()
    d.observe_snapshot()
    advance(181)
    d.evaluate()
    # push through recovery rounds so escalated would be armed on next fail
    for _ in range(3):
        d.note_recovery()
    advance(181)
    d.evaluate()
    assert d.stall_escalated is True
    d.observe_snapshot()
    assert d.push_state == "verified"
    assert d.stall_escalated is False
    assert d.stall_detected is False


def test_escalated_after_max_recovery_rounds() -> None:
    make, advance, _ = _make_fakes()
    d = make()
    d.observe_snapshot()
    advance(181)
    d.evaluate()  # pushing
    assert d.push_state == "pushing"
    assert d.stall_escalated is False
    for _ in range(2):
        d.note_recovery()
        advance(181)
        d.evaluate()
    # 3rd round crosses max
    d.note_recovery()
    advance(181)
    d.evaluate()
    assert d.stall_escalated is True


def test_note_recovery_only_counts_in_pushing() -> None:
    make, _, _ = _make_fakes()
    d = make()
    d.observe_snapshot()  # verified
    d.note_recovery()
    d.note_recovery()
    assert d.stall_escalated is False  # no counting in verified


def test_on_change_fires_transitions() -> None:
    make, advance, _ = _make_fakes()
    changes: list[str] = []
    d = StallDetector(
        source="qmt",
        window=ActivityWindow(env_value="09:15-11:30,13:00-15:00", now=lambda: _at(10, 0)),
        stall_grace_seconds=180.0,
        max_recovery_cycles=3,
        now=lambda: 1000.0,
        on_change=lambda s: changes.append(s),
    )
    d.evaluate()  # pushing
    d.observe_snapshot()  # verified
    assert changes == ["pushing", "verified"]
