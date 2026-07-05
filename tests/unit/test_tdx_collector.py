import asyncio
import inspect
import logging
from typing import Any

import pytest

from src.adapter_legacy.mock.tdx_mock import TdxLegacyMockAdapter
from src.datasource.tdx_legacy.bridge import TdxLegacyBridge
from src.datasource.tdx_legacy.collector import TdxLegacyMinuteCollector
from src.datasource.tdx_legacy.subscription import TdxLegacySubscriptionClient
from src.datasource.tdx_models import TdxBar, TdxSnapshot
from tdx.main import app


class FakeProvider:
    def __init__(self) -> None:
        self.snapshot_calls: list[list[str]] = []
        self.bar_calls: list[tuple[list[str], str, int]] = []

    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        _ = fields
        self.snapshot_calls.append(list(symbols))
        return [
            TdxSnapshot(
                symbol=symbol,
                last=10.25,
                open=10.0,
                high=10.5,
                low=9.9,
                lastClose=9.95,
                volume=1500,
                amount=15375.0,
                provider="tdx",
                asOf="2026-06-29T14:55:01+08:00",
            )
            for symbol in symbols
        ]

    async def collect_recent_bars(self, symbols, period, count):
        self.bar_calls.append((list(symbols), period, count))
        _ = count
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


class SnapshotProvider(FakeProvider):
    pass


class MixedProvider:
    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot | dict[str, Any]]:
        _ = fields
        return [
            TdxSnapshot(
                symbol=symbols[0],
                last=10.25,
                open=10.0,
                high=10.5,
                low=9.9,
                lastClose=9.95,
                volume=1500,
                amount=15375.0,
                provider="tdx",
                asOf="2026-06-29T14:55:01+08:00",
            ),
            {
                "symbol": symbols[0],
                "last": 10.3,
                "open": 10.0,
                "high": 10.5,
                "low": 9.9,
                "lastClose": 9.95,
                "volume": 1600,
                "amount": 16480.0,
                "provider": "tdx",
                "asOf": "2026-06-29T14:55:02+08:00",
            },
        ]

    async def collect_recent_bars(self, symbols, period, count):
        _ = count
        return [
            TdxBar(
                symbol=symbols[0],
                period=period,
                barTime="2026-06-26T09:31:00+08:00",
                open=10.1,
                high=10.3,
                low=10.0,
                close=10.2,
                volume=1200,
                amount=12345.6,
                provider="tdx",
                receivedAt="2026-06-26T09:31:02+08:00",
            ),
            {
                "symbol": symbols[0],
                "period": period,
                "barTime": "2026-06-26T09:32:00+08:00",
                "open": 10.2,
                "high": 10.5,
                "low": 10.1,
                "close": 10.4,
                "volume": 1300,
                "amount": 13345.6,
                "provider": "tdx",
                "receivedAt": "2026-06-26T09:32:02+08:00",
            },
        ]


class MultiSymbolProvider:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        _ = fields
        self.calls.append(list(symbols))
        return [
            TdxSnapshot(
                symbol=symbol,
                last=10.2 + index,
                open=10.0 + index,
                high=10.5 + index,
                low=9.9 + index,
                lastClose=9.95 + index,
                volume=1500 + index,
                amount=15375.0 + index,
                provider="tdx",
                asOf=f"2026-06-29T14:5{index}:01+08:00",
            )
            for index, symbol in enumerate(symbols, start=1)
        ]

    async def collect_recent_bars(self, symbols, period, count):
        self.calls.append((list(symbols), period, count))
        return [
            {
                "symbol": symbol,
                "period": period,
                "barTime": f"2026-06-26T09:3{index}:00+08:00",
                "open": 10.1 + index,
                "high": 10.3 + index,
                "low": 10.0 + index,
                "close": 10.2 + index,
                "volume": 1200 + index,
                "amount": 12345.6 + index,
                "provider": "tdx",
                "receivedAt": f"2026-06-26T09:3{index}:02+08:00",
            }
            for index, symbol in enumerate(symbols, start=1)
        ]


class CountingProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[list[str]] = []

    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        self.calls.append(list(symbols))
        return await super().get_snapshots(symbols, fields)

    async def collect_recent_bars(self, symbols, period, count):
        self.calls.append((list(symbols), period, count))
        return await super().collect_recent_bars(symbols, period, count)


class DuplicateProvider:
    async def collect_recent_bars(self, symbols, period, count):
        _ = (symbols, period, count)
        return [
            {
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
            {
                "symbol": "600519.SH",
                "period": "1m",
                "barTime": "2026-06-26T09:31:00+08:00",
                "open": 10.9,
                "high": 11.3,
                "low": 10.0,
                "close": 11.2,
                "volume": 9999,
                "amount": 99999.9,
                "provider": "tdx",
                "receivedAt": "2026-06-26T09:31:05+08:00",
            },
            {
                "symbol": "600519.SH",
                "period": "1m",
                "barTime": "2026-06-26T09:31:00+08:00",
                "open": 10.1,
                "high": 10.3,
                "low": 10.0,
                "close": 10.2,
                "volume": 1200,
                "amount": 12345.6,
                "provider": "alternate",
                "receivedAt": "2026-06-26T09:31:02+08:00",
            },
        ]


class EmptyProvider:
    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        _ = (symbols, fields)
        return []

    async def collect_recent_bars(self, symbols, period, count):
        _ = (symbols, period, count)
        return []


class RaisingProvider:
    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        _ = (symbols, fields)
        raise RuntimeError("tdx snapshot failed")

    async def collect_recent_bars(self, symbols, period, count):
        _ = (symbols, period, count)
        raise RuntimeError("tdx http failed")


class CallbackCollector:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    def mark_dirty_from_callback(self, payload: dict[str, Any]) -> None:
        self.payloads.append(payload)


class CallbackAdapter:
    def __init__(self) -> None:
        self.callback: Any | None = None
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.snapshot_calls: list[str] = []

    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
        self.subscribed.extend(stock_list)
        self.callback = callback

    async def unsubscribe_hq(self, stock_list: list[str] | None = None) -> None:
        if stock_list is None:
            self.unsubscribed.extend(self.subscribed)
            self.subscribed.clear()
            return
        self.unsubscribed.extend(stock_list)
        requested = set(stock_list)
        self.subscribed = [symbol for symbol in self.subscribed if symbol not in requested]

    async def get_market_snapshot(
        self,
        stock_code: str,
        field_list: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = field_list
        self.snapshot_calls.append(stock_code)
        return {"Code": stock_code}


class CapacityEnforcingAdapter:
    def __init__(self, *, max_active: int, active: list[str]) -> None:
        self.max_active = max_active
        self.active = list(active)
        self.operations: list[tuple[str, list[str]]] = []
        self.fail_on_subscribe_symbols: set[str] = set()
        self.callback: Any | None = None

    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
        if self.fail_on_subscribe_symbols.intersection(stock_list):
            raise RuntimeError("subscribe failed")
        if len(self.active) + len(stock_list) > self.max_active:
            raise RuntimeError("subscription cap exceeded")
        self.operations.append(("subscribe", stock_list))
        self.active.extend(stock_list)
        self.callback = callback

    async def unsubscribe_hq(self, stock_list: list[str] | None = None) -> None:
        if stock_list is None:
            stock_list = list(self.active)
        self.operations.append(("unsubscribe", stock_list))
        self.active = [symbol for symbol in self.active if symbol not in set(stock_list)]


class BlockingSubscribeAdapter:
    def __init__(self) -> None:
        self.subscribe_started = asyncio.Event()
        self.release_first_subscribe = asyncio.Event()
        self.subscribe_calls: list[list[str]] = []

    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
        _ = callback
        self.subscribe_calls.append(stock_list)
        if len(self.subscribe_calls) == 1:
            self.subscribe_started.set()
            await self.release_first_subscribe.wait()

    async def unsubscribe_hq(self, stock_list: list[str] | None = None) -> None:
        _ = stock_list


class PartialUnsubscribeAdapter:
    def __init__(self) -> None:
        self.active = ["600519.SH", "000001.SZ"]
        self.subscribe_calls: list[list[str]] = []

    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
        _ = callback
        self.subscribe_calls.append(stock_list)
        self.active.extend(stock for stock in stock_list if stock not in self.active)

    async def unsubscribe_hq(self, stock_list: list[str] | None = None) -> None:
        requested = set(stock_list or self.active)
        self.active = [stock for stock in self.active if stock not in requested]
        raise RuntimeError("unsubscribe failed")


class RollbackFailingAdapter:
    def __init__(self) -> None:
        self.active = ["600519.SH"]

    async def subscribe_hq(self, stock_list: list[str], callback: Any = None) -> None:
        _ = callback
        if stock_list == ["000001.SZ"]:
            raise RuntimeError("subscribe failed")
        raise RuntimeError("rollback failed")

    async def unsubscribe_hq(self, stock_list: list[str] | None = None) -> None:
        requested = set(stock_list or self.active)
        self.active = [stock for stock in self.active if stock not in requested]


class FakeAdapter:
    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_called = False

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


@pytest.mark.asyncio
async def test_callback_only_marks_dirty_symbol():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    collector = TdxLegacyMinuteCollector(provider=FakeProvider(), bridge=bridge, period="1m")

    collector.mark_dirty_from_callback({"Code": "SH600519", "ErrorId": "0"})

    assert collector.dirty_symbols == {"600519.SH"}


@pytest.mark.asyncio
async def test_callback_dirty_symbol_is_scheduled_on_event_loop():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    collector = TdxLegacyMinuteCollector(provider=FakeProvider(), bridge=bridge, period="1m")
    await collector.start()

    collector.mark_dirty_from_callback({"Code": "SH600519", "ErrorId": "0"})

    assert collector.dirty_symbols == set()
    await asyncio.sleep(0)
    assert collector.dirty_symbols == {"600519.SH"}
    await collector.stop()


@pytest.mark.asyncio
async def test_collector_collects_dirty_snapshot_once():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    provider = FakeProvider()
    collector = TdxLegacyMinuteCollector(provider=provider, bridge=bridge, period="1m")
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()
    emitted_again = await collector.collect_dirty_once()

    assert emitted == 1
    assert emitted_again == 0
    assert provider.snapshot_calls == [["600519.SH"]]
    assert provider.bar_calls == []
    assert bridge.event_queue_depth == 0
    assert bridge.last_callback_at is not None


@pytest.mark.asyncio
async def test_collector_publishes_new_normalized_snapshot():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    published: list[TdxSnapshot] = []

    async def publish_snapshot(snapshot: TdxSnapshot) -> None:
        published.append(snapshot)

    collector = TdxLegacyMinuteCollector(
        provider=FakeProvider(),
        bridge=bridge,
        period="1m",
        snapshot_publisher=publish_snapshot,
    )
    collector.mark_dirty("SH600519")

    emitted = await collector.collect_dirty_once()

    assert emitted == 1
    assert published[0].model_dump(by_alias=True) == {
        "symbol": "600519.SH",
        "last": 10.25,
        "open": 10.0,
        "high": 10.5,
        "low": 9.9,
        "lastClose": 9.95,
        "volume": 1500.0,
        "amount": 15375.0,
        "provider": "tdx",
        "asOf": "2026-06-29T14:55:01+08:00",
    }


@pytest.mark.asyncio
async def test_collector_publishes_snapshot_without_fetching_cached_bars():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    provider = SnapshotProvider()
    published: list[str] = []

    async def publish_snapshot(snapshot: TdxSnapshot) -> None:
        published.append(snapshot.symbol)

    collector = TdxLegacyMinuteCollector(
        provider=provider,
        bridge=bridge,
        period="1m",
        snapshot_publisher=publish_snapshot,
    )
    collector.mark_dirty("SH600519")

    emitted = await collector.collect_dirty_once()

    assert emitted == 1
    assert provider.snapshot_calls == [["600519.SH"]]
    assert provider.bar_calls == []
    assert published == ["600519.SH"]
    assert bridge.event_queue_depth == 0


@pytest.mark.asyncio
async def test_collector_publishes_all_dirty_snapshots_without_bar_backpressure():
    bridge = TdxLegacyBridge(queue_max_size=1, max_subscriptions=100)
    provider = MultiSymbolProvider()
    published: list[TdxSnapshot] = []

    async def publish_snapshot(snapshot: TdxSnapshot) -> None:
        published.append(snapshot)

    collector = TdxLegacyMinuteCollector(
        provider=provider,
        bridge=bridge,
        period="1m",
        snapshot_publisher=publish_snapshot,
    )
    collector.mark_dirty("600519.SH")
    collector.mark_dirty("000001.SZ")

    emitted = await collector.collect_dirty_once()

    assert emitted == 2
    assert [snapshot.symbol for snapshot in published] == ["000001.SZ", "600519.SH"]
    assert bridge.event_queue_depth == 0
    assert bridge.last_error_code is None


@pytest.mark.asyncio
async def test_collector_discards_dirty_symbols_when_active_subscriptions_are_known_empty():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    bridge.mark_active([])
    provider = CountingProvider()

    collector = TdxLegacyMinuteCollector(
        provider=provider,
        bridge=bridge,
        period="1m",
    )
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()

    assert emitted == 0
    assert provider.calls == []
    assert collector.dirty_symbols == set()


@pytest.mark.asyncio
async def test_collector_keeps_unknown_subscription_state_conservative():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    provider = CountingProvider()
    collector = TdxLegacyMinuteCollector(provider=provider, bridge=bridge, period="1m")
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()

    assert emitted == 1
    assert provider.calls == [["600519.SH"]]
    assert provider.bar_calls == []


@pytest.mark.asyncio
async def test_collector_records_snapshot_publish_error_and_allows_retry():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    publish_calls: list[str] = []

    async def failing_publish_snapshot(snapshot: TdxSnapshot) -> None:
        publish_calls.append(snapshot.symbol)
        raise RuntimeError("publish failed")

    collector = TdxLegacyMinuteCollector(
        provider=FakeProvider(),
        bridge=bridge,
        period="1m",
        snapshot_publisher=failing_publish_snapshot,
    )
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()
    collector.mark_dirty("600519.SH")
    emitted_again = await collector.collect_dirty_once()

    assert emitted == 1
    assert emitted_again == 1
    assert publish_calls == ["600519.SH", "600519.SH"]
    assert collector.state == "error"
    assert collector.last_error_code == "TDX_COLLECTOR_PUBLISH_ERROR"


@pytest.mark.asyncio
async def test_subscription_client_enforces_max_subscriptions_with_stable_error():
    adapter = CallbackAdapter()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=2)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=CallbackCollector(),
        max_subscriptions=2,
    )

    result = await client.subscribe(["SH600519", "SZ000001", "SH601318"])

    assert result == {
        "accepted": [],
        "rejected": ["600519.SH", "000001.SZ", "601318.SH"],
        "active": [],
        "error": {
            "code": "TDX_SUBSCRIBE_LIMIT_EXCEEDED",
            "message": "Cannot subscribe to more than 2 symbols",
            "retryable": False,
            "details": {"maxSubscriptions": 2},
        },
    }
    assert adapter.subscribed == []


def test_subscription_client_preserves_zero_max_subscription_override():
    client = TdxLegacySubscriptionClient(
        adapter=CallbackAdapter(),
        bridge=TdxLegacyBridge(queue_max_size=10, max_subscriptions=100),
        collector=CallbackCollector(),
        max_subscriptions=0,
    )

    assert client.max_subscriptions == 0


@pytest.mark.asyncio
async def test_subscription_callback_marks_dirty_without_collecting_bars():
    adapter = CallbackAdapter()
    collector = CallbackCollector()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=collector,
        max_subscriptions=100,
    )

    await client.subscribe(["600519.SH"])
    assert adapter.callback is not None
    adapter.callback({"Code": "SH600519", "ErrorId": "0"})
    await asyncio.sleep(0)

    assert collector.payloads == [{"Code": "SH600519", "ErrorId": "0"}]
    assert adapter.snapshot_calls == []


@pytest.mark.asyncio
async def test_subscription_callback_records_accepted_quote_diagnostics(caplog):
    adapter = CallbackAdapter()
    collector = CallbackCollector()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=collector,
        max_subscriptions=100,
    )

    await client.subscribe(["600519.SH"])
    assert adapter.callback is not None

    with caplog.at_level(logging.INFO, logger="src.datasource.tdx_legacy.subscription"):
        adapter.callback({"Code": "SH600519", "ErrorId": "0"})

    health = bridge.health()
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 0
    assert health["last_quote_callback_code"] == "SH600519"
    assert health["last_quote_callback_symbol"] == "600519.SH"
    assert health["last_quote_callback_accepted"] is True
    assert health["last_quote_callback_reject_reason"] is None
    assert "TDX quote callback accepted" in caplog.text
    assert "symbol=600519.SH" in caplog.text


@pytest.mark.asyncio
async def test_subscription_callback_accepts_official_json_string_payload(caplog):
    adapter = CallbackAdapter()
    collector = CallbackCollector()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=collector,
        max_subscriptions=100,
    )

    await client.subscribe(["600519.SH"])
    assert adapter.callback is not None

    with caplog.at_level(logging.INFO, logger="src.datasource.tdx_legacy.subscription"):
        adapter.callback('{"Code":"SH600519","ErrorId":"0"}')
    await asyncio.sleep(0)

    health = bridge.health()
    assert collector.payloads == [{"Code": "SH600519", "ErrorId": "0"}]
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 0
    assert health["last_quote_callback_code"] == "SH600519"
    assert health["last_quote_callback_symbol"] == "600519.SH"
    assert health["last_quote_callback_accepted"] is True
    assert health["last_quote_callback_reject_reason"] is None
    assert "TDX quote callback accepted" in caplog.text


@pytest.mark.asyncio
async def test_subscription_callback_records_inactive_quote_diagnostics(caplog):
    adapter = CallbackAdapter()
    collector = CallbackCollector()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=collector,
        max_subscriptions=100,
    )

    await client.subscribe(["600519.SH"])
    assert adapter.callback is not None

    with caplog.at_level(logging.WARNING, logger="src.datasource.tdx_legacy.subscription"):
        adapter.callback({"Code": "SZ000001", "ErrorId": "0"})

    health = bridge.health()
    assert collector.payloads == []
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 1
    assert health["last_quote_callback_code"] == "SZ000001"
    assert health["last_quote_callback_symbol"] == "000001.SZ"
    assert health["last_quote_callback_accepted"] is False
    assert health["last_quote_callback_reject_reason"] == "inactive_subscription"
    assert "TDX quote callback rejected" in caplog.text
    assert "reason=inactive_subscription" in caplog.text


@pytest.mark.asyncio
async def test_subscription_callback_records_malformed_quote_diagnostics(caplog):
    adapter = CallbackAdapter()
    collector = CallbackCollector()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=collector,
        max_subscriptions=100,
    )

    await client.subscribe(["600519.SH"])
    assert adapter.callback is not None

    with caplog.at_level(logging.WARNING, logger="src.datasource.tdx_legacy.subscription"):
        adapter.callback({"ErrorId": "0"})

    health = bridge.health()
    assert collector.payloads == []
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 1
    assert health["last_quote_callback_code"] is None
    assert health["last_quote_callback_symbol"] is None
    assert health["last_quote_callback_accepted"] is False
    assert health["last_quote_callback_reject_reason"] == "missing_code"
    assert "reason=missing_code" in caplog.text


@pytest.mark.asyncio
async def test_subscription_callback_records_invalid_json_string_diagnostics(caplog):
    adapter = CallbackAdapter()
    collector = CallbackCollector()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=collector,
        max_subscriptions=100,
    )

    await client.subscribe(["600519.SH"])
    assert adapter.callback is not None

    with caplog.at_level(logging.WARNING, logger="src.datasource.tdx_legacy.subscription"):
        adapter.callback("not-json")

    health = bridge.health()
    assert collector.payloads == []
    assert health["quote_callback_count"] == 1
    assert health["quote_callback_rejected_count"] == 1
    assert health["last_quote_callback_code"] is None
    assert health["last_quote_callback_symbol"] is None
    assert health["last_quote_callback_accepted"] is False
    assert health["last_quote_callback_reject_reason"] == "invalid_payload"
    assert "reason=invalid_payload" in caplog.text


def test_subscription_client_has_no_synchronous_compatibility_callback_hook():
    signature = inspect.signature(TdxLegacySubscriptionClient)

    assert "compatibility_callback" not in signature.parameters


@pytest.mark.asyncio
async def test_subscription_client_replaces_symbols_without_exceeding_adapter_capacity():
    adapter = CapacityEnforcingAdapter(
        max_active=2,
        active=["600519.SH", "000001.SZ"],
    )
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=2)
    bridge.mark_active(["600519.SH", "000001.SZ"])
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=CallbackCollector(),
        max_subscriptions=2,
    )

    result = await client.sync(["601318.SH", "000858.SZ"])

    assert result["error"] is None
    assert adapter.operations[0][0] == "unsubscribe"
    assert adapter.operations[1] == ("subscribe", ["601318.SH", "000858.SZ"])
    assert adapter.active == ["601318.SH", "000858.SZ"]
    assert bridge.active_subscriptions == ["601318.SH", "000858.SZ"]


@pytest.mark.asyncio
async def test_subscription_client_limit_check_uses_active_state_after_waiting_for_lock():
    adapter = BlockingSubscribeAdapter()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=1)
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=CallbackCollector(),
        max_subscriptions=1,
    )

    first = asyncio.create_task(client.subscribe(["600519.SH"]))
    await adapter.subscribe_started.wait()
    second = asyncio.create_task(client.subscribe(["000001.SZ"]))

    adapter.release_first_subscribe.set()
    first_result = await first
    second_result = await second

    assert first_result["accepted"] == ["600519.SH"]
    assert second_result["error"]["code"] == "TDX_SUBSCRIBE_LIMIT_EXCEEDED"
    assert adapter.subscribe_calls == [["600519.SH"]]
    assert bridge.active_subscriptions == ["600519.SH"]


@pytest.mark.asyncio
async def test_subscription_client_rolls_back_active_state_when_sync_subscribe_fails():
    adapter = CapacityEnforcingAdapter(
        max_active=2,
        active=["600519.SH"],
    )
    adapter.fail_on_subscribe_symbols = {"000001.SZ"}
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=2)
    bridge.mark_active(["600519.SH"])
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=CallbackCollector(),
        max_subscriptions=2,
    )

    with pytest.raises(RuntimeError, match="subscribe failed"):
        await client.sync(["000001.SZ"])

    assert adapter.active == ["600519.SH"]
    assert bridge.active_subscriptions == ["600519.SH"]


@pytest.mark.asyncio
async def test_subscription_client_restores_bridge_and_adapter_after_partial_unsubscribe_failure():
    adapter = PartialUnsubscribeAdapter()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=2)
    bridge.mark_active(["600519.SH", "000001.SZ"])
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=CallbackCollector(),
        max_subscriptions=2,
    )

    with pytest.raises(RuntimeError, match="unsubscribe failed"):
        await client.sync(["601318.SH"])

    assert bridge.active_subscriptions == ["600519.SH", "000001.SZ"]
    assert adapter.active == ["600519.SH", "000001.SZ"]


@pytest.mark.asyncio
async def test_subscription_client_rollback_failure_does_not_mask_original_exception():
    adapter = RollbackFailingAdapter()
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=2)
    bridge.mark_active(["600519.SH"])
    client = TdxLegacySubscriptionClient(
        adapter=adapter,
        bridge=bridge,
        collector=CallbackCollector(),
        max_subscriptions=2,
    )

    with pytest.raises(RuntimeError, match="subscribe failed"):
        await client.sync(["000001.SZ"])

    assert bridge.active_subscriptions == ["600519.SH"]


@pytest.mark.asyncio
async def test_collector_does_not_use_bar_duplicate_keys_for_snapshots():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    provider = FakeProvider()
    collector = TdxLegacyMinuteCollector(provider=provider, bridge=bridge, period="1m")
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()

    assert emitted == 1
    assert provider.bar_calls == []


@pytest.mark.asyncio
async def test_collector_accepts_dicts_and_tdx_snapshot_models():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    collector = TdxLegacyMinuteCollector(provider=MixedProvider(), bridge=bridge, period="1m")
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()

    assert emitted == 2
    assert bridge.event_queue_depth == 0


@pytest.mark.asyncio
async def test_collector_records_stale_state_when_no_snapshots_are_returned():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    collector = TdxLegacyMinuteCollector(provider=EmptyProvider(), bridge=bridge, period="1m")
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()

    assert emitted == 0
    assert collector.state == "stale"
    assert collector.last_error_code == "TDX_COLLECTOR_STALE"
    assert collector.stale_symbols == {"600519.SH"}


@pytest.mark.asyncio
async def test_collector_records_error_state_when_provider_raises():
    bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)
    collector = TdxLegacyMinuteCollector(provider=RaisingProvider(), bridge=bridge, period="1m")
    collector.mark_dirty("600519.SH")

    emitted = await collector.collect_dirty_once()

    assert emitted == 0
    assert collector.state == "error"
    assert collector.last_error_code == "TDX_COLLECTOR_SNAPSHOT_ERROR"
    assert collector.stale_symbols == {"600519.SH"}


@pytest.mark.asyncio
async def test_mock_adapter_emit_hq_update_triggers_stored_callback():
    adapter = TdxLegacyMockAdapter()
    payloads: list[dict[str, str]] = []

    await adapter.subscribe_hq(["600519.SH"], payloads.append)
    await adapter.emit_hq_update("SH600519")

    assert payloads == [{"Code": "SH600519", "ErrorId": "0"}]


@pytest.mark.asyncio
async def test_lifespan_creates_runtime_without_overwriting_injected_fakes(monkeypatch):
    import tdx.main

    previous_adapter = tdx.main.tdx_legacy_adapter
    previous_provider = tdx.main.tdx_provider
    previous_bridge = tdx.main.tdx_legacy_bridge
    previous_collector = tdx.main.tdx_legacy_collector
    previous_subscription_client = getattr(tdx.main, "tdx_legacy_subscription_client", None)
    previous_owned_provider = tdx.main._tdx_provider_owned_by_main
    previous_owned_bridge = getattr(tdx.main, "_tdx_legacy_bridge_owned_by_main", None)
    previous_owned_collector = getattr(tdx.main, "_tdx_legacy_collector_owned_by_main", None)
    previous_owned_subscription_client = getattr(
        tdx.main,
        "_tdx_legacy_subscription_client_owned_by_main",
        None,
    )

    fake_adapter = FakeAdapter()
    fake_provider = FakeProvider()
    fake_bridge = TdxLegacyBridge(queue_max_size=10, max_subscriptions=100)

    async def injected_snapshot_publisher(snapshot: TdxSnapshot) -> None:
        _ = snapshot

    fake_collector = TdxLegacyMinuteCollector(
        provider=fake_provider,
        bridge=fake_bridge,
        period="1m",
        collect_delay_seconds=999,
        snapshot_publisher=injected_snapshot_publisher,
    )
    monkeypatch.setattr(tdx.main, "create_tdx_legacy_adapter", lambda: fake_adapter)
    tdx.main.tdx_legacy_adapter = None
    tdx.main.tdx_provider = fake_provider
    tdx.main.tdx_legacy_bridge = fake_bridge
    tdx.main.tdx_legacy_collector = fake_collector
    tdx.main.tdx_legacy_subscription_client = None

    try:
        async with tdx.main.lifespan(app):
            assert tdx.main.tdx_legacy_adapter is fake_adapter
            assert tdx.main.tdx_provider is fake_provider
            assert tdx.main.tdx_legacy_bridge is fake_bridge
            assert tdx.main.tdx_legacy_collector is fake_collector
            assert fake_collector.snapshot_publisher is injected_snapshot_publisher
            assert tdx.main.tdx_legacy_subscription_client is not None
            assert fake_collector._task is not None
            assert not fake_collector._task.done()

        assert fake_adapter.shutdown_called is True
        assert fake_collector.state == "stopped"
        assert tdx.main.tdx_legacy_adapter is None
        assert tdx.main.tdx_provider is fake_provider
        assert tdx.main.tdx_legacy_bridge is fake_bridge
        assert tdx.main.tdx_legacy_collector is fake_collector
        assert fake_collector.snapshot_publisher is injected_snapshot_publisher
        assert tdx.main.tdx_legacy_subscription_client is None
    finally:
        tdx.main.tdx_legacy_adapter = previous_adapter
        tdx.main.tdx_provider = previous_provider
        tdx.main.tdx_legacy_bridge = previous_bridge
        tdx.main.tdx_legacy_collector = previous_collector
        tdx.main.tdx_legacy_subscription_client = previous_subscription_client
        tdx.main._tdx_provider_owned_by_main = previous_owned_provider
        tdx.main._tdx_legacy_bridge_owned_by_main = previous_owned_bridge
        tdx.main._tdx_legacy_collector_owned_by_main = previous_owned_collector
        tdx.main._tdx_legacy_subscription_client_owned_by_main = previous_owned_subscription_client
