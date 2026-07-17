"""Deterministic cross-repository replay app using production QMT wiring."""

from datetime import datetime
from zoneinfo import ZoneInfo

from qmt.main import create_qmt_app

REPLAY_NOW = datetime(2026, 7, 14, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

app = create_qmt_app(
    realtime_mode="builtin_experimental",
    collector_now=lambda: REPLAY_NOW,
)
