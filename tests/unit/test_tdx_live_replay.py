from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.datasource.tdx.realtime.contract import validate_tdx_realtime_native_snapshot

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "tdx"


def load_live_fixture(name: str) -> Any:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def test_replays_captured_live_market_snapshot_through_realtime_contract() -> None:
    fixture = load_live_fixture("live_market_snapshot_600519.json")
    snapshot = validate_tdx_realtime_native_snapshot(
        fixture["symbol"],
        fixture["nativePayload"],
        expected_code=fixture["symbol"],
    )

    assert snapshot.symbol == "600519.SH"
    assert snapshot.eventTime == "2026-06-29T15:00:00+08:00"
    assert snapshot.last == 1418.0
    assert snapshot.high == 1426.5
    assert snapshot.low == 1406.0
    assert snapshot.nativeVolume == "3138308"
    assert snapshot.nativeAmount == "4446039416.0"
