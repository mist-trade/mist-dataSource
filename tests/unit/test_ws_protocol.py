"""Unit tests for WebSocket protocol."""

from datetime import datetime

from src.ws.protocol import WSMessage


def test_ws_message_creation():
    """Test creating a WSMessage."""
    msg = WSMessage(type="quote", data={"symbol": "SH600519", "price": 1800.0})
    assert msg.type == "quote"
    assert msg.data["symbol"] == "SH600519"
    assert msg.data["price"] == 1800.0
    assert datetime.fromisoformat(msg.timestamp)  # Validate timestamp format


def test_ws_message_to_json():
    """Test converting WSMessage to JSON."""
    msg = WSMessage(type="heartbeat", data={})
    json_str = msg.to_json()
    assert isinstance(json_str, str)
    assert "heartbeat" in json_str
