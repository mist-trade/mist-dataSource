"""Unit tests for the TDX runtime composition boundary."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI

from src.datasource.tdx.runtime import TdxRuntime


class FakeAdapter:
    def __init__(self, events: list[str], *, fail_initialize: bool = False) -> None:
        self.events = events
        self.fail_initialize = fail_initialize
        self.initialized = False
        self.shutdown_called = False

    async def initialize(self) -> None:
        self.events.append("adapter.initialize")
        self.initialized = True
        if self.fail_initialize:
            raise RuntimeError("adapter failed")

    async def shutdown(self) -> None:
        self.events.append("adapter.shutdown")
        self.shutdown_called = True


class FakeProvider:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.closed = False

    async def aclose(self) -> None:
        self.events.append("provider.aclose")
        self.closed = True


class FakeHealthyProvider(FakeProvider):
    async def health(self) -> dict[str, Any]:
        return {"tdxHttpReachable": True, "lastError": None}


class FakeCollector:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.events.append("collector.start")
        self.started = True

    async def stop(self) -> None:
        self.events.append("collector.stop")
        self.stopped = True


class FakeBridge:
    pass


class FakeSubscriptionClient:
    pass


class FakeWsManager:
    connection_count = 0


class FakeHealthBridge:
    def health(self) -> dict[str, Any]:
        return {
            "subscribed_count": 2,
            "active_subscriptions": ["600519.SH", "000001.SZ"],
            "last_callback_at": "2026-07-03T09:30:00+08:00",
            "last_minute_bar_at": "2026-07-03T09:31:00+08:00",
            "quote_callback_count": 3,
            "quote_callback_rejected_count": 1,
            "last_quote_callback_at": "2026-07-03T09:30:01+08:00",
            "last_quote_callback_code": "SH600519",
            "last_quote_callback_symbol": "600519.SH",
            "last_quote_callback_accepted": True,
            "last_quote_callback_reject_reason": None,
            "event_queue_depth": 4,
            "event_queue_capacity": 10,
        }


class FakeHealthCollector:
    last_minute_bar_at = "2026-07-03T09:32:00+08:00"
    event_queue_depth = 5
    event_queue_capacity = 20
    state = "running"


class FakeConnectedWsManager:
    connection_count = 1


class FakeRaisingHealthProvider:
    async def health(self) -> dict[str, Any]:
        raise RuntimeError("provider health failed")


def _runtime(events: list[str]) -> TdxRuntime:
    return TdxRuntime(
        adapter_factory=lambda: FakeAdapter(events),
        provider_factory=lambda: FakeProvider(events),
        bridge_factory=lambda: FakeBridge(),
        collector_factory=lambda _provider, _bridge, _publisher: FakeCollector(events),
        subscription_client_factory=lambda _adapter, _bridge, _collector: FakeSubscriptionClient(),
        ws_manager_factory=lambda: FakeWsManager(),
    )


@pytest.mark.asyncio
async def test_runtime_startup_creates_components_and_syncs_app_state() -> None:
    events: list[str] = []
    runtime = _runtime(events)
    app = FastAPI()

    await runtime.start()
    runtime.sync_app_state(app)

    assert events == ["adapter.initialize", "collector.start"]
    assert isinstance(app.state.tdx_adapter, FakeAdapter)
    assert isinstance(app.state.tdx_provider, FakeProvider)
    assert isinstance(app.state.tdx_bridge, FakeBridge)
    assert isinstance(app.state.tdx_collector, FakeCollector)
    assert isinstance(app.state.tdx_subscription_client, FakeSubscriptionClient)
    assert isinstance(app.state.ws_manager, FakeWsManager)

    await runtime.stop()
    assert events == [
        "adapter.initialize",
        "collector.start",
        "collector.stop",
        "provider.aclose",
        "adapter.shutdown",
    ]


@pytest.mark.asyncio
async def test_runtime_preserves_injected_components_on_shutdown() -> None:
    events: list[str] = []
    adapter = FakeAdapter(events)
    provider = FakeProvider(events)
    collector = FakeCollector(events)
    runtime = TdxRuntime(
        adapter=adapter,
        provider=provider,
        bridge=FakeBridge(),
        collector=collector,
        subscription_client=FakeSubscriptionClient(),
        ws_manager=FakeWsManager(),
    )

    await runtime.start()
    await runtime.stop()

    assert events == ["collector.start", "collector.stop"]
    assert adapter.shutdown_called is False
    assert provider.closed is False


@pytest.mark.asyncio
async def test_runtime_cleans_owned_components_when_startup_fails() -> None:
    events: list[str] = []
    runtime = TdxRuntime(
        adapter_factory=lambda: FakeAdapter(events, fail_initialize=True),
        provider_factory=lambda: FakeProvider(events),
        bridge_factory=lambda: FakeBridge(),
        collector_factory=lambda _provider, _bridge, _publisher: FakeCollector(events),
        subscription_client_factory=lambda _adapter, _bridge, _collector: FakeSubscriptionClient(),
        ws_manager_factory=lambda: FakeWsManager(),
    )

    with pytest.raises(RuntimeError, match="adapter failed"):
        await runtime.start()

    assert events == ["adapter.initialize", "adapter.shutdown"]


def test_runtime_sync_app_state_can_clear_components() -> None:
    events: list[str] = []
    runtime = _runtime(events)
    app = FastAPI()

    runtime.sync_app_state(app)

    assert app.state.tdx_adapter is None
    assert app.state.tdx_provider is None
    assert app.state.tdx_bridge is None
    assert app.state.tdx_collector is None
    assert app.state.tdx_subscription_client is None
    assert isinstance(app.state.ws_manager, FakeWsManager)


@pytest.mark.asyncio
async def test_runtime_health_reports_enriched_component_state() -> None:
    events: list[str] = []
    runtime = TdxRuntime(
        adapter=FakeAdapter(events),
        provider=FakeHealthyProvider(events),
        bridge=FakeHealthBridge(),
        collector=FakeHealthCollector(),
        subscription_client=FakeSubscriptionClient(),
        ws_manager=FakeConnectedWsManager(),
    )

    health = await runtime.health(instance="tdx")

    assert health["status"] == "ok"
    assert health["instance"] == "tdx"
    assert health["adapter"] == "FakeAdapter"
    assert health["connections"] == 1
    assert health["tdxHttpReachable"] is True
    assert health["tqInitialized"] is True
    assert health["wsConnected"] is True
    assert health["subscribedCount"] == 2
    assert health["activeSubscriptions"] == ["600519.SH", "000001.SZ"]
    assert health["lastCallbackAt"] == "2026-07-03T09:30:00+08:00"
    assert health["quoteCallbackCount"] == 3
    assert health["quoteCallbackRejectedCount"] == 1
    assert health["lastQuoteCallbackCode"] == "SH600519"
    assert health["lastQuoteCallbackSymbol"] == "600519.SH"
    assert health["lastQuoteCallbackAccepted"] is True
    assert health["lastQuoteCallbackRejectReason"] is None
    assert health["lastMinuteBarAt"] == "2026-07-03T09:32:00+08:00"
    assert health["eventQueueDepth"] == 5
    assert health["eventQueueCapacity"] == 20
    assert health["collectorState"] == "running"


@pytest.mark.asyncio
async def test_runtime_health_surfaces_provider_health_failure() -> None:
    runtime = TdxRuntime(
        provider=FakeRaisingHealthProvider(),
        ws_manager=FakeWsManager(),
    )

    health = await runtime.health()

    assert health["tdxHttpReachable"] is False
    assert health["tdxProviderError"] == "provider health failed"
    assert health["tdxProviderErrorType"] == "RuntimeError"


@pytest.mark.asyncio
async def test_runtime_health_uses_bridge_state_when_collector_is_absent() -> None:
    events: list[str] = []
    runtime = TdxRuntime(
        adapter=FakeAdapter(events),
        provider=FakeHealthyProvider(events),
        bridge=FakeHealthBridge(),
        collector=None,
        subscription_client=FakeSubscriptionClient(),
        ws_manager=FakeWsManager(),
    )

    health = await runtime.health()

    assert health["collectorState"] == "not_started"
    assert health["lastMinuteBarAt"] == "2026-07-03T09:31:00+08:00"
    assert health["eventQueueDepth"] == 4
    assert health["eventQueueCapacity"] == 10
