"""WebSocket integration tests for TDX service.

Tests WebSocket connection, ping/pong, and subscription functionality.
"""

import asyncio
from queue import Empty, Queue
from threading import Thread
from typing import Any

import pytest
from starlette.testclient import TestClient

from src.core.config import settings
from tdx.main import app


class CallbackCapturingAdapter:
    def __init__(self) -> None:
        self.callback: Any | None = None
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.fail_on_subscribe_symbols: set[str] = set()
        self.fail_snapshot = False
        self.snapshot_calls: list[str] = []

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
        if self.fail_on_subscribe_symbols.intersection(stock_list):
            raise RuntimeError("subscribe failed")
        self.subscribed = [*self.subscribed, *stock_list]
        self.callback = callback

    async def unsubscribe_hq(self, stock_list: list[str]) -> None:
        self.unsubscribed.extend(stock_list)
        self.subscribed = [stock for stock in self.subscribed if stock not in set(stock_list)]

    async def get_market_snapshot(
        self, stock_code: str, _field_list: list[str] | None = None
    ) -> dict[str, Any]:
        self.snapshot_calls.append(stock_code)
        if self.fail_snapshot:
            raise RuntimeError("snapshot failed")
        return {"Code": stock_code, "Last": 10.2}


class FakeRealtimeProvider:
    def __init__(self) -> None:
        self.collect_calls: list[tuple[list[str], str, int]] = []
        self.snapshot_calls: list[list[str]] = []
        self.fail_snapshot = False

    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        _ = fields
        self.snapshot_calls.append(list(symbols))
        if self.fail_snapshot:
            raise RuntimeError("snapshot failed")
        return [
            {
                "symbol": symbol,
                "last": 10.25,
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "lastClose": 9.95,
                "volume": 1500,
                "amount": 15375.0,
                "provider": "tdx",
                "asOf": "2026-06-29T14:55:01+08:00",
            }
            for symbol in symbols
        ]

    async def collect_recent_bars(
        self,
        symbols: list[str],
        period: str,
        count: int,
    ) -> list[dict[str, Any]]:
        self.collect_calls.append((symbols, period, count))
        return [
            {
                "symbol": symbol,
                "period": period,
                "barTime": "2026-06-26T09:31:00+08:00",
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "volume": 1200,
                "amount": 12345.6,
                "provider": "tdx",
                "receivedAt": "2026-06-26T09:31:02+08:00",
            }
            for symbol in symbols
        ]

    async def health(self) -> dict[str, Any]:
        return {"tdxHttpReachable": True}

    async def aclose(self) -> None:
        pass


class ObservedSubscriptionClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str] | None]] = []
        self.active: list[str] = []

    async def subscribe(self, symbols: list[str]) -> dict[str, Any]:
        self.calls.append(("subscribe", symbols))
        self.active = [*self.active, *symbols]
        return {"accepted": symbols, "rejected": [], "active": self.active, "error": None}

    async def sync(self, symbols: list[str]) -> dict[str, Any]:
        self.calls.append(("sync", symbols))
        self.active = list(symbols)
        return {"accepted": symbols, "rejected": [], "active": self.active, "error": None}

    async def unsubscribe(self, symbols: list[str] | None = None) -> dict[str, Any]:
        self.calls.append(("unsubscribe", symbols))
        requested = set(symbols or self.active)
        self.active = [symbol for symbol in self.active if symbol not in requested]
        return {
            "accepted": list(symbols or requested),
            "rejected": [],
            "active": self.active,
            "error": None,
        }


@pytest.fixture
def client():
    """Create TestClient with lifespan (adapter initialization)."""
    import tdx.main

    previous_adapter = tdx.main.tdx_legacy_adapter
    previous_provider = tdx.main.tdx_provider
    previous_bridge = tdx.main.tdx_legacy_bridge
    previous_collector = tdx.main.tdx_legacy_collector
    previous_subscription_client = tdx.main.tdx_legacy_subscription_client
    previous_owned_adapter = tdx.main._tdx_legacy_adapter_owned_by_main
    previous_owned_provider = tdx.main._tdx_provider_owned_by_main
    previous_owned_bridge = tdx.main._tdx_legacy_bridge_owned_by_main
    previous_owned_collector = tdx.main._tdx_legacy_collector_owned_by_main
    previous_owned_subscription_client = tdx.main._tdx_legacy_subscription_client_owned_by_main
    try:
        with TestClient(app) as client:
            yield client
    finally:
        tdx.main.tdx_legacy_adapter = previous_adapter
        tdx.main.tdx_provider = previous_provider
        tdx.main.tdx_legacy_bridge = previous_bridge
        tdx.main.tdx_legacy_collector = previous_collector
        tdx.main.tdx_legacy_subscription_client = previous_subscription_client
        tdx.main._tdx_legacy_adapter_owned_by_main = previous_owned_adapter
        tdx.main._tdx_provider_owned_by_main = previous_owned_provider
        tdx.main._tdx_legacy_bridge_owned_by_main = previous_owned_bridge
        tdx.main._tdx_legacy_collector_owned_by_main = previous_owned_collector
        tdx.main._tdx_legacy_subscription_client_owned_by_main = previous_owned_subscription_client


def test_ws_ping_pong(client):
    """Test WebSocket ping/pong heartbeat."""
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"
        assert data["provider"] == "tdx"
        assert data["data"] == {}
        assert "timestamp" in data


def test_ws_subscribe_within_limit(client):
    """Test WebSocket subscription with <= 100 stocks succeeds."""
    stocks = [f"60000{i}.SH" for i in range(10)]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "subscribed"
        assert data["data"]["accepted"] == stocks
        assert "stocks" not in data


def test_ws_subscribe_exceeds_limit(client):
    """Test WebSocket subscription with > 100 stocks returns error."""
    stocks = [f"60000{i}.SH" for i in range(101)]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "error"


def test_ws_unsubscribe(client):
    """Test WebSocket unsubscribe."""
    stocks = ["600519.SH"]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "subscribe", "stocks": stocks})
        ws.receive_json()  # subscribed response

        ws.send_json({"type": "unsubscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "unsubscribed"


def test_ws_disconnect(client):
    """Test WebSocket disconnect is handled gracefully."""
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "ping"})
        ws.receive_json()

    # Connection should close cleanly


def test_ws_sends_ready_on_connect(client):
    with client.websocket_connect("/ws/quote/test-client") as ws:
        data = ws.receive_json()
        assert data["type"] == "ready"
        assert data["provider"] == "tdx"
        assert "timestamp" in data
        assert "active" in data["data"]


def test_ws_sync_subscriptions_returns_accepted_symbols(client):
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()  # ready
        ws.send_json({"type": "sync_subscriptions", "symbols": ["600519.SH"]})
        data = ws.receive_json()
        assert data["type"] == "subscribed"
        assert data["data"]["accepted"] == ["600519.SH"]


def test_ws_rejects_non_leader_sync(client):
    with client.websocket_connect("/ws/quote/leader") as leader:
        leader.receive_json()
        with client.websocket_connect("/ws/quote/follower") as follower:
            follower.receive_json()
            follower.send_json({"type": "sync_subscriptions", "symbols": ["600519.SH"]})
            data = follower.receive_json()
            assert data["type"] == "error"
            assert data["data"]["code"] == "DATASOURCE_WS_NOT_LEADER"
            assert data["data"]["retryable"] is False


def test_ws_rejects_duplicate_client_id_without_closing_original(client):
    with client.websocket_connect("/ws/quote/same-client") as original:
        original.receive_json()

        with client.websocket_connect("/ws/quote/same-client") as duplicate:
            data = duplicate.receive_json()

        assert data["type"] == "error"
        assert data["provider"] == "tdx"
        assert data["data"]["code"] == "DATASOURCE_WS_DUPLICATE_CLIENT"
        assert data["data"]["details"]["clientId"] == "same-client"

        original.send_json({"type": "ping"})
        assert original.receive_json()["type"] == "pong"


def test_ws_health_uses_bridge_queue_capacity_when_collector_absent(client):
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["collectorState"] == "not_started"
    assert body["eventQueueCapacity"] == settings.tdx.ws_queue_max_size


def test_ws_invalid_json_returns_structured_error(client):
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()
        ws.send_text("{")
        data = ws.receive_json()

    assert data["type"] == "error"
    assert data["provider"] == "tdx"
    assert data["data"]["code"] == "DATASOURCE_WS_INVALID_MESSAGE"
    assert data["data"]["retryable"] is False


def test_ws_rejects_non_list_symbols_payload(client):
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.receive_json()
        ws.send_json({"type": "subscribe", "stocks": "600519.SH"})
        data = ws.receive_json()

    assert data["type"] == "error"
    assert data["provider"] == "tdx"
    assert data["data"]["code"] == "DATASOURCE_WS_INVALID_SYMBOLS"


def test_ws_subscription_commands_go_through_subscription_client(monkeypatch):
    import tdx.main

    subscription_client = ObservedSubscriptionClient()
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", subscription_client)

    with (
        TestClient(app) as callback_client,
        callback_client.websocket_connect("/ws/quote/subscription-client") as ws,
    ):
        ws.receive_json()

        ws.send_json({"type": "sync_subscriptions", "symbols": ["600519.SH"]})
        assert ws.receive_json()["type"] == "subscribed"

        ws.send_json({"type": "subscribe", "stocks": ["000001.SZ"]})
        assert ws.receive_json()["type"] == "subscribed"

        ws.send_json({"type": "unsubscribe", "stocks": ["600519.SH"]})
        assert ws.receive_json()["type"] == "unsubscribed"

    assert subscription_client.calls == [
        ("sync", ["600519.SH"]),
        ("subscribe", ["000001.SZ"]),
        ("unsubscribe", ["600519.SH"]),
    ]


def test_ws_callback_marks_dirty_and_collector_emits_snapshot_quote(monkeypatch):
    import tdx.main

    adapter = CallbackCapturingAdapter()
    provider = FakeRealtimeProvider()
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: adapter)
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: provider)
    monkeypatch.setattr(tdx.main, "tdx_legacy_bridge", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_collector", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", None)

    with (
        TestClient(app) as callback_client,
        callback_client.websocket_connect("/ws/quote/callback-client") as ws,
    ):
        ws.receive_json()
        ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
        assert ws.receive_json()["type"] == "subscribed"
        assert adapter.callback is not None

        received: Queue[tuple[str, Any]] = Queue()

        def receive_message() -> None:
            try:
                received.put(("ok", ws.receive_json()))
            except Exception as exc:
                received.put(("error", exc))

        Thread(target=receive_message, daemon=True).start()
        adapter.callback({"Code": "SH600519", "ErrorId": "0"})

        callback_client.portal.call(asyncio.sleep, 0)
        assert tdx.main.tdx_legacy_collector.dirty_symbols == {"600519.SH"}
        assert provider.snapshot_calls == []
        with pytest.raises(Empty):
            received.get(timeout=0.2)

        callback_client.portal.call(tdx.main.tdx_legacy_collector.collect_dirty_once)

        try:
            status, payload = received.get(timeout=2)
        except Empty:
            pytest.fail("quote was not received after collector collected dirty symbol")

        assert status == "ok", payload
        assert payload["type"] == "quote"
        assert payload["provider"] == "tdx"
        assert "timestamp" in payload
        assert payload["data"]["stock_code"] == "600519.SH"
        assert payload["data"]["snapshot"]["Code"] == "600519.SH"
        assert payload["data"]["snapshot"]["Now"] == 10.25
        assert payload["data"]["snapshot"]["LastClose"] == 9.95
        assert "Last" not in payload["data"]["snapshot"]
        assert "Max" not in payload["data"]["snapshot"]
        assert "Min" not in payload["data"]["snapshot"]
        assert provider.snapshot_calls == [["600519.SH"]]
        assert provider.collect_calls == []

        health = callback_client.get("/health").json()
        assert health["lastCallbackAt"] is not None


def test_ws_collector_publishes_snapshot_quote_only(monkeypatch):
    import tdx.main

    adapter = CallbackCapturingAdapter()
    provider = FakeRealtimeProvider()
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: adapter)
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: provider)
    monkeypatch.setattr(tdx.main, "tdx_legacy_bridge", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_collector", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", None)

    with (
        TestClient(app) as callback_client,
        callback_client.websocket_connect("/ws/quote/bar-client") as ws,
    ):
        ws.receive_json()
        ws.send_json({"type": "sync_subscriptions", "symbols": ["600519.SH"]})
        assert ws.receive_json()["type"] == "subscribed"
        assert adapter.callback is not None

        adapter.callback({"Code": "SH600519", "ErrorId": "0"})
        callback_client.portal.call(tdx.main.tdx_legacy_collector.collect_dirty_once)

        quote_payload = ws.receive_json()

    assert quote_payload["type"] == "quote"
    assert quote_payload["provider"] == "tdx"
    assert "timestamp" in quote_payload
    assert quote_payload["data"]["stock_code"] == "600519.SH"
    assert quote_payload["data"]["snapshot"]["Code"] == "600519.SH"
    assert quote_payload["data"]["snapshot"]["Now"] == 10.25
    assert "Last" not in quote_payload["data"]["snapshot"]
    assert "Max" not in quote_payload["data"]["snapshot"]
    assert "Min" not in quote_payload["data"]["snapshot"]
    assert provider.snapshot_calls == [["600519.SH"]]
    assert provider.collect_calls == []


def test_ws_callback_after_disconnect_does_not_update_bridge_health(monkeypatch):
    import tdx.main

    adapter = CallbackCapturingAdapter()
    provider = FakeRealtimeProvider()
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: adapter)
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: provider)
    monkeypatch.setattr(tdx.main, "tdx_legacy_bridge", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_collector", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", None)

    with TestClient(app) as callback_client:
        with callback_client.websocket_connect("/ws/quote/closing-client") as ws:
            ws.receive_json()
            ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
            assert ws.receive_json()["type"] == "subscribed"
            assert adapter.callback is not None

        adapter.callback({"Code": "600519.SH", "ErrorId": "0"})
        health = callback_client.get("/health").json()

    assert health["lastCallbackAt"] is None
    assert tdx.main.tdx_legacy_collector is None


def test_ws_callback_after_unsubscribe_is_ignored(monkeypatch):
    import tdx.main

    adapter = CallbackCapturingAdapter()
    provider = FakeRealtimeProvider()
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: adapter)
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: provider)
    monkeypatch.setattr(tdx.main, "tdx_legacy_bridge", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_collector", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", None)

    with (
        TestClient(app) as callback_client,
        callback_client.websocket_connect("/ws/quote/unsubscribe-client") as ws,
    ):
        ws.receive_json()
        ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
        assert ws.receive_json()["type"] == "subscribed"
        assert adapter.callback is not None

        ws.send_json({"type": "unsubscribe", "stocks": ["600519.SH"]})
        assert ws.receive_json()["type"] == "unsubscribed"

        adapter.callback({"Code": "600519.SH", "ErrorId": "0"})
        health = callback_client.get("/health").json()

    assert health["lastCallbackAt"] is None
    assert tdx.main.tdx_legacy_collector is None


def test_ws_subscription_failure_restores_previous_active_state(monkeypatch):
    import tdx.main

    adapter = CallbackCapturingAdapter()
    provider = FakeRealtimeProvider()
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: adapter)
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: provider)
    monkeypatch.setattr(tdx.main, "tdx_legacy_bridge", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_collector", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", None)

    with (
        TestClient(app) as callback_client,
        callback_client.websocket_connect("/ws/quote/transaction-client") as ws,
    ):
        ws.receive_json()
        ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
        assert ws.receive_json()["type"] == "subscribed"

        adapter.fail_on_subscribe_symbols = {"000001.SZ"}
        ws.send_json({"type": "sync_subscriptions", "symbols": ["000001.SZ"]})
        data = ws.receive_json()

        assert data["type"] == "error"
        assert data["data"]["code"] == "TDX_SUBSCRIPTION_FAILED"
        assert adapter.subscribed == ["600519.SH"]

        health = callback_client.get("/health").json()
        assert health["subscribedCount"] == 1


def test_ws_message_protocol_accepts_bar_type():
    from src.ws.protocol import WSMessage

    message = WSMessage(
        type="bar",
        data={
            "symbol": "600519.SH",
            "period": "1m",
            "barTime": "2026-06-26T09:31:00+08:00",
            "open": 10.1,
            "high": 10.3,
            "low": 10.0,
            "close": 10.2,
            "volume": 1200,
            "amount": 12345.6,
            "provider": "tdx",
            "receivedAt": "2026-06-26T09:31:02+08:00",
        },
    )

    assert message.type == "bar"


def test_ws_snapshot_failure_records_collector_error_without_marketdata_fallback(monkeypatch):
    import tdx.main

    adapter = CallbackCapturingAdapter()
    provider = FakeRealtimeProvider()
    provider.fail_snapshot = True
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: adapter)
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: provider)
    monkeypatch.setattr(tdx.main, "tdx_legacy_bridge", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_collector", None)
    monkeypatch.setattr(tdx.main, "tdx_legacy_subscription_client", None)

    with (
        TestClient(app) as callback_client,
        callback_client.websocket_connect("/ws/quote/failing-quote-client") as ws,
    ):
        ws.receive_json()
        ws.send_json({"type": "subscribe", "stocks": ["600519.SH"]})
        assert ws.receive_json()["type"] == "subscribed"
        assert adapter.callback is not None

        adapter.callback({"Code": "600519.SH", "ErrorId": "0"})
        emitted = callback_client.portal.call(tdx.main.tdx_legacy_collector.collect_dirty_once)

        assert emitted == 0
        assert provider.snapshot_calls == [["600519.SH"]]
        assert provider.collect_calls == []
        assert tdx.main.tdx_legacy_collector.last_error_code == "TDX_COLLECTOR_SNAPSHOT_ERROR"
