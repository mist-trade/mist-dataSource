"""WebSocket contract tests for QMT service."""

from collections.abc import AsyncIterator
from typing import Any

from starlette.testclient import TestClient

from qmt.main import app


class FakeQmtAdapter:
    def __init__(self) -> None:
        self.subscribed: list[str] = []

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def subscribe_quote(self, stocks: list[str]) -> AsyncIterator[dict[str, Any]]:
        self.subscribed = list(stocks)
        if False:
            yield {}


def test_qmt_ws_ping_returns_timestamped_pong(monkeypatch):
    import qmt.main

    with TestClient(app) as client:
        monkeypatch.setattr(qmt.main, "qmt_adapter", FakeQmtAdapter())
        app.state.qmt_adapter = qmt.main.qmt_adapter
        with client.websocket_connect("/ws/quote/qmt-client") as ws:
            ws.send_json({"type": "ping"})
            payload = ws.receive_json()

    assert payload["type"] == "pong"
    assert payload["provider"] == "qmt"
    assert payload["data"] == {}
    assert "timestamp" in payload


def test_qmt_ws_adapter_unavailable_uses_canonical_error(monkeypatch):
    import qmt.main

    with TestClient(app) as client:
        monkeypatch.setattr(qmt.main, "qmt_adapter", None)
        app.state.qmt_adapter = None
        with client.websocket_connect("/ws/quote/qmt-client") as ws:
            ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
            payload = ws.receive_json()

    assert payload["type"] == "error"
    assert payload["provider"] == "qmt"
    assert payload["data"]["code"] == "QMT_ADAPTER_UNAVAILABLE"
    assert payload["data"]["message"] == "Adapter not initialized"
    assert payload["data"]["retryable"] is True


def test_qmt_ws_subscription_ack_uses_data_payload(monkeypatch):
    import qmt.main

    adapter = FakeQmtAdapter()
    with TestClient(app) as client:
        monkeypatch.setattr(qmt.main, "qmt_adapter", adapter)
        app.state.qmt_adapter = adapter
        with client.websocket_connect("/ws/quote/qmt-client") as ws:
            ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
            payload = ws.receive_json()

    assert payload["type"] == "subscribed"
    assert payload["provider"] == "qmt"
    assert payload["data"] == {
        "accepted": ["600519.SH"],
        "rejected": [],
        "active": ["600519.SH"],
    }
    assert "stocks" not in payload
