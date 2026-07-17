"""Unit tests for WebSocket protocol."""

from datetime import datetime

from src.ws.protocol import (
    WSMessage,
    ws_error,
    ws_experimental_snapshot,
    ws_pong,
    ws_quote,
    ws_ready,
    ws_stream_started,
    ws_subscription_ack,
)


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


def test_ws_ready_and_quote_helpers_share_common_envelope():
    ready = ws_ready(provider="tdx", data={"active": []})
    quote = ws_quote(
        provider="tdx",
        data={
            "stock_code": "600519.SH",
            "snapshot": {"Code": "600519.SH", "Now": 10.25},
        },
    )

    assert ready.type == "ready"
    assert ready.provider == "tdx"
    assert ready.data == {"active": []}
    assert quote.type == "quote"
    assert quote.provider == "tdx"
    assert quote.data["snapshot"]["Now"] == 10.25


def test_experimental_ws_factories_keep_snapshot_and_epoch_events_isolated():
    snapshot = ws_experimental_snapshot("tdx", {"sequence": 7, "streamEpoch": "epoch-1"})
    started = ws_stream_started(
        "tdx",
        {
            "streamEpoch": "epoch-2",
            "generation": 2,
            "mode": "builtin_experimental",
            "ownerId": "owner-2",
            "bridgeBuildId": "build-2",
        },
    )

    assert snapshot.type == "tdx.experimental.snapshot"
    assert snapshot.type != "quote"
    assert snapshot.data == {"sequence": 7, "streamEpoch": "epoch-1"}
    assert started.type == "stream_started"
    assert started.data["streamEpoch"] == "epoch-2"
    assert started.data["generation"] == 2
    assert started.data["ownerId"] == "owner-2"
    assert started.data["bridgeBuildId"] == "build-2"
