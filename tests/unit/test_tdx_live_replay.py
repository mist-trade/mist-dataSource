from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.datasource.tdx.provider import TdxDatasourceProvider

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "tdx"


class ReplayTdxHttpClient:
    def __init__(self, responses: dict[str, Any]):
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any] | list[Any] | None]] = []

    async def call(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> Any:
        self.calls.append((method, params))
        return self.responses[method]


def load_live_fixture(name: str) -> Any:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_replays_captured_live_market_snapshot_without_tdx_runtime() -> None:
    fixture = load_live_fixture("live_market_snapshot_600519.json")
    fake_client = ReplayTdxHttpClient({"get_market_snapshot": fixture["nativePayload"]})
    provider = TdxDatasourceProvider(fake_client)

    snapshots = await provider.get_snapshots([fixture["symbol"]], fields=None)

    assert fake_client.calls == [
        (
            "get_market_snapshot",
            {
                "stock_code": "600519.SH",
                "field_list": [],
            },
        )
    ]
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.symbol == "600519.SH"
    assert snapshot.provider == "tdx"
    assert snapshot.asOf == "2026-06-29T15:00:00+08:00"
    assert snapshot.last == 1418.0
    assert snapshot.high == 1426.5
    assert snapshot.low == 1406.0
    assert snapshot.volume == 3138308.0
