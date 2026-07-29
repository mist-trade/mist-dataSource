"""Unit tests for WebSocket protocol."""

from datetime import datetime

from src.ws.protocol import (
    WSMessage,
    ws_error,
    ws_pong,
    ws_ready,
    ws_realtime_snapshot,
    ws_subscription_ack,
)


def test_ws_message_creation():
    """Test creating a WSMessage."""
    msg = WSMessage(type="realtime.ready", data={"symbol": "SH600519", "price": 1800.0})
    assert msg.type == "realtime.ready"
    assert msg.data["symbol"] == "SH600519"
    assert msg.data["price"] == 1800.0
    assert datetime.fromisoformat(msg.timestamp)  # Validate timestamp format


def test_ws_message_to_json():
    """Test converting WSMessage to JSON."""
    msg = WSMessage(type="ping", data={})
    json_str = msg.to_json()
    assert isinstance(json_str, str)
    assert "ping" in json_str


def test_ws_pong_helper_emits_timestamped_provider_envelope():
    msg = ws_pong(provider="tdx")

    assert msg.type == "pong"
    assert msg.provider == "tdx"
    assert msg.data == {}
    assert datetime.fromisoformat(msg.timestamp)


def test_ws_error_helper_emits_machine_readable_data_payload():
    msg = ws_error(
        provider="qmt",
        code="QMT_ADAPTER_UNAVAILABLE",
        message="Adapter not initialized",
        retryable=True,
        details={"clientId": "client-a"},
    )

    assert msg.type == "error"
    assert msg.provider == "qmt"
    assert msg.data == {
        "code": "QMT_ADAPTER_UNAVAILABLE",
        "message": "Adapter not initialized",
        "retryable": True,
        "details": {"clientId": "client-a"},
    }


def test_ws_subscription_ack_helper_keeps_ack_fields_under_data():
    msg = ws_subscription_ack(
        provider="tdx",
        msg_type="subscribed",
        accepted=["600519.SH"],
        rejected=[],
        active=["600519.SH"],
    )

    assert msg.type == "subscribed"
    assert msg.provider == "tdx"
    assert msg.data == {
        "accepted": ["600519.SH"],
        "rejected": [],
        "active": ["600519.SH"],
    }


def test_ws_ready_helper_uses_common_envelope():
    ready = ws_ready(provider="tdx", data={"active": []})

    assert ready.type == "realtime.ready"
    assert ready.provider == "tdx"
    assert ready.data == {"active": []}


def test_realtime_snapshot_factory_uses_the_formal_native_event():
    snapshot = ws_realtime_snapshot("tdx", {"sequence": 7, "streamEpoch": "epoch-1"})
    qmt_snapshot = ws_realtime_snapshot("qmt", {"sequence": 1, "streamEpoch": "qmt-epoch-1"})

    assert snapshot.type == "realtime.native_snapshot"
    assert snapshot.type != "quote"
    assert snapshot.data == {"sequence": 7, "streamEpoch": "epoch-1"}
    assert qmt_snapshot.type == "realtime.native_snapshot"
    assert qmt_snapshot.provider == "qmt"
