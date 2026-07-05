from src.datasource.tdx_legacy.bridge import TdxLegacyBridge
from src.datasource.tdx_models import TdxBar


def test_bridge_claims_first_client_as_command_leader():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)

    assert bridge.claim_leader("nestjs-a") is True
    assert bridge.claim_leader("nestjs-b") is False


def test_bridge_releases_leader_on_disconnect():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    bridge.claim_leader("nestjs-a")

    bridge.disconnect("nestjs-a")

    assert bridge.claim_leader("nestjs-b") is True


def test_bridge_sync_subscriptions_calculates_delta():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    result = bridge.plan_sync(["600519.SH", "000001.SZ"])

    assert result.to_subscribe == ["600519.SH", "000001.SZ"]
    assert result.to_unsubscribe == []

    bridge.mark_active(["600519.SH", "000001.SZ"])
    result = bridge.plan_sync(["600519.SH"])

    assert result.to_subscribe == []
    assert result.to_unsubscribe == ["000001.SZ"]


def test_bridge_rejects_subscription_over_limit():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=2)

    result = bridge.plan_sync(["600519.SH", "000001.SZ", "601318.SH"])

    assert result.error_code == "TDX_SUBSCRIBE_LIMIT_EXCEEDED"


def test_bridge_bounded_queue_reports_backpressure():
    bridge = TdxLegacyBridge(queue_max_size=1, max_subscriptions=100)
    bar = TdxBar(
        symbol="600519.SH",
        period="1m",
        barTime="2026-06-26T09:31:00+08:00",
        open=10.1,
        high=10.3,
        low=10.0,
        close=10.2,
        volume=1200,
        amount=12345.6,
        provider="tdx",
        receivedAt="2026-06-26T09:31:02+08:00",
    )

    assert bridge.enqueue_bar(bar) is True
    assert bridge.enqueue_bar(bar) is True
    assert bridge.last_error_code == "DATASOURCE_WS_BACKPRESSURE"
    assert bridge.event_queue_depth == 1


def test_bridge_records_runtime_callback_and_queue_state():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)

    bridge.record_callback(last_minute_bar_at="2026-06-26T09:31:00+08:00")
    bridge.record_queue_depth(3)

    health = bridge.health()
    assert health["last_callback_at"] is not None
    assert health["last_minute_bar_at"] == "2026-06-26T09:31:00+08:00"
    assert health["event_queue_depth"] == 3


def test_bridge_records_raw_quote_callback_diagnostics():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    bridge.mark_active(["600519.SH"])

    bridge.record_quote_callback(
        code="SH600519",
        normalized_symbol="600519.SH",
        accepted=True,
        reject_reason=None,
    )

    health = bridge.health()
    assert health["active_subscriptions"] == ["600519.SH"]
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 0
    assert health["last_quote_callback_at"] is not None
    assert health["last_quote_callback_code"] == "SH600519"
    assert health["last_quote_callback_symbol"] == "600519.SH"
    assert health["last_quote_callback_accepted"] is True
    assert health["last_quote_callback_reject_reason"] is None


def test_bridge_records_rejected_quote_callback_diagnostics():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)

    bridge.record_quote_callback(
        code="SZ000001",
        normalized_symbol="000001.SZ",
        accepted=False,
        reject_reason="inactive_subscription",
    )

    health = bridge.health()
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 1
    assert health["last_quote_callback_code"] == "SZ000001"
    assert health["last_quote_callback_symbol"] == "000001.SZ"
    assert health["last_quote_callback_accepted"] is False
    assert health["last_quote_callback_reject_reason"] == "inactive_subscription"


def test_bridge_reports_route_backpressure_without_enqueueing_bar():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)

    bridge.report_backpressure()

    assert bridge.last_error_code == "DATASOURCE_WS_BACKPRESSURE"
