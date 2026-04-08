"""WebSocket integration tests for TDX service.

Tests WebSocket connection, ping/pong, and subscription functionality.
"""

import pytest
from starlette.testclient import TestClient

from tdx.main import app


@pytest.fixture
def client():
    """Create TestClient with lifespan (adapter initialization)."""
    with TestClient(app) as client:
        yield client


def test_ws_ping_pong(client):
    """Test WebSocket ping/pong heartbeat."""
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"


def test_ws_subscribe_within_limit(client):
    """Test WebSocket subscription with <= 100 stocks succeeds."""
    stocks = [f"60000{i}.SH" for i in range(10)]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "subscribed"


def test_ws_subscribe_exceeds_limit(client):
    """Test WebSocket subscription with > 100 stocks returns error."""
    stocks = [f"60000{i}.SH" for i in range(101)]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "error"


def test_ws_unsubscribe(client):
    """Test WebSocket unsubscribe."""
    stocks = ["600519.SH"]

    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "subscribe", "stocks": stocks})
        ws.receive_json()  # subscribed response

        ws.send_json({"type": "unsubscribe", "stocks": stocks})
        data = ws.receive_json()
        assert data["type"] == "unsubscribed"


def test_ws_disconnect(client):
    """Test WebSocket disconnect is handled gracefully."""
    with client.websocket_connect("/ws/quote/test-client") as ws:
        ws.send_json({"type": "ping"})
        ws.receive_json()

    # Connection should close cleanly
