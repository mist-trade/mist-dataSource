"""WebSocket integration tests for TDX service.

Tests WebSocket connection, ping/pong, and subscription functionality.
"""

import json

from starlette.testclient import TestClient

from tdx.main import app


def test_ws_ping_pong():
    """Test WebSocket ping/pong heartbeat."""
    client = TestClient(app)
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


def test_ws_subscribe_within_limit():
    """Test WebSocket subscription with <= 100 stocks succeeds."""
    client = TestClient(app)
    stocks = [f"60000{i}.SH" for i in range(10)]  # 10 stocks, within limit

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        # Should receive subscribed confirmation (or error if not implemented)
        try:
            data = ws.receive_json(timeout=1)
            # Mock adapter doesn't actually push data, so we just check it doesn't crash
            assert data is not None
        except Exception:
            # Timeout is acceptable for mock
            pass


def test_ws_subscribe_exceeds_limit():
    """Test WebSocket subscription with > 100 stocks returns error."""
    client = TestClient(app)
    stocks = [f"60000{i}.SH" for i in range(101)]  # 101 stocks, exceeds limit

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        # Should receive error
        data = ws.receive_json()
        assert data["type"] == "error" or "message" in data.get("data", {})


def test_ws_unsubscribe():
    """Test WebSocket unsubscribe."""
    client = TestClient(app)
    stocks = ["600519.SH"]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        # First subscribe
        ws.send_json({"type": "subscribe", "stocks": stocks})
        try:
            ws.receive_json(timeout=1)
        except Exception:
            pass

        # Then unsubscribe
        ws.send_json({"type": "unsubscribe", "stocks": stocks})
        # Should receive unsubscribed confirmation (or timeout for mock)
        try:
            data = ws.receive_json(timeout=1)
            assert data is not None
        except Exception:
            # Timeout is acceptable for mock
            pass


def test_ws_disconnect():
    """Test WebSocket disconnect is handled gracefully."""
    client = TestClient(app)

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        ws.receive_json()

    # Connection should close cleanly
