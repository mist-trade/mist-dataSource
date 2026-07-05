from collections.abc import Callable, Mapping
from typing import Any, cast

from fastapi import FastAPI

from src.adapter_legacy import create_tdx_legacy_adapter
from src.core.config import settings
from src.datasource.tdx_legacy.bridge import TdxLegacyBridge
from src.datasource.tdx_legacy.collector import TdxLegacyMinuteCollector
from src.datasource.tdx_legacy.subscription import TdxLegacySubscriptionClient
from src.datasource.tdx_models import TdxSnapshot
from src.datasource.tdx_provider import TdxDatasourceProvider
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_quote

AdapterFactory = Callable[[], Any]
ProviderFactory = Callable[[], Any]
BridgeFactory = Callable[[], Any]
CollectorFactory = Callable[[Any, Any, Callable[[TdxSnapshot], Any]], Any]
SubscriptionClientFactory = Callable[[Any, Any, Any], Any]
WsManagerFactory = Callable[[], Any]


class TdxRuntime:
    def __init__(
        self,
        *,
        adapter: Any | None = None,
        provider: Any | None = None,
        bridge: Any | None = None,
        collector: Any | None = None,
        subscription_client: Any | None = None,
        ws_manager: Any | None = None,
        adapter_factory: AdapterFactory = create_tdx_legacy_adapter,
        provider_factory: ProviderFactory = TdxDatasourceProvider,
        bridge_factory: BridgeFactory | None = None,
        collector_factory: CollectorFactory | None = None,
        subscription_client_factory: SubscriptionClientFactory | None = None,
        ws_manager_factory: WsManagerFactory = ConnectionManager,
    ) -> None:
        self.adapter = adapter
        self.provider = provider
        self.bridge = bridge
        self.collector = collector
        self.subscription_client = subscription_client
        self.ws_manager = ws_manager or ws_manager_factory()

        self._adapter_factory = adapter_factory
        self._provider_factory = provider_factory
        self._bridge_factory = bridge_factory or self._default_bridge_factory
        self._collector_factory = collector_factory or self._default_collector_factory
        self._subscription_client_factory = (
            subscription_client_factory or self._default_subscription_client_factory
        )

        self._owns_adapter = adapter is None
        self._owns_provider = provider is None
        self._owns_bridge = bridge is None
        self._owns_collector = collector is None
        self._owns_subscription_client = subscription_client is None

    async def start(self) -> None:
        try:
            if self.adapter is None:
                self.adapter = self._adapter_factory()
                self._owns_adapter = True
                await self.adapter.initialize()

            if self.provider is None:
                self.provider = self._provider_factory()
                self._owns_provider = True

            if self.bridge is None:
                self.bridge = self._bridge_factory()
                self._owns_bridge = True

            if self.collector is None:
                self.collector = self._collector_factory(
                    self.provider,
                    self.bridge,
                    self._publish_collector_snapshot,
                )
                self._owns_collector = True

            if self.subscription_client is None:
                self.subscription_client = self._subscription_client_factory(
                    self.adapter,
                    self.bridge,
                    self.collector,
                )
                self._owns_subscription_client = True

            if hasattr(self.collector, "start"):
                await self.collector.start()
        except Exception:
            await self.stop()
            raise

    @property
    def owns_adapter(self) -> bool:
        return self._owns_adapter

    @property
    def owns_provider(self) -> bool:
        return self._owns_provider

    @property
    def owns_bridge(self) -> bool:
        return self._owns_bridge

    @property
    def owns_collector(self) -> bool:
        return self._owns_collector

    @property
    def owns_subscription_client(self) -> bool:
        return self._owns_subscription_client

    async def stop(self) -> None:
        owned_subscription_client = (
            self.subscription_client if self._owns_subscription_client else None
        )
        owned_collector = self.collector if self._owns_collector else None
        owned_bridge = self.bridge if self._owns_bridge else None
        owned_provider = self.provider if self._owns_provider else None
        owned_adapter = self.adapter if self._owns_adapter else None

        try:
            try:
                try:
                    if self.collector is not None and hasattr(self.collector, "stop"):
                        await self.collector.stop()
                finally:
                    if self.subscription_client is owned_subscription_client:
                        self.subscription_client = None
                    self._owns_subscription_client = False
                    if self.collector is owned_collector:
                        self.collector = None
                    self._owns_collector = False
                    if self.bridge is owned_bridge:
                        self.bridge = None
                    self._owns_bridge = False

                if owned_provider is not None and hasattr(owned_provider, "aclose"):
                    await owned_provider.aclose()
            finally:
                if self.provider is owned_provider:
                    self.provider = None
                self._owns_provider = False
        finally:
            try:
                if owned_adapter is not None and hasattr(owned_adapter, "shutdown"):
                    await owned_adapter.shutdown()
            finally:
                if self.adapter is owned_adapter:
                    self.adapter = None
                self._owns_adapter = False

    def sync_app_state(self, target_app: FastAPI) -> None:
        target_app.state.tdx_runtime = self
        target_app.state.tdx_legacy_adapter = self.adapter
        target_app.state.tdx_provider = self.provider
        target_app.state.tdx_legacy_bridge = self.bridge
        target_app.state.tdx_legacy_collector = self.collector
        target_app.state.tdx_legacy_subscription_client = self.subscription_client
        target_app.state.ws_manager = self.ws_manager

    def _default_bridge_factory(self) -> TdxLegacyBridge:
        return TdxLegacyBridge(
            queue_max_size=settings.tdx.ws_queue_max_size,
            max_subscriptions=settings.tdx.max_subscriptions,
        )

    def _default_collector_factory(
        self,
        provider: Any,
        bridge: Any,
        snapshot_publisher: Callable[[TdxSnapshot], Any],
    ) -> TdxLegacyMinuteCollector:
        return TdxLegacyMinuteCollector(
            provider=provider,
            bridge=bridge,
            period=settings.tdx.minute_period,
            snapshot_publisher=snapshot_publisher,
        )

    def _default_subscription_client_factory(
        self,
        adapter: Any,
        bridge: Any,
        collector: Any,
    ) -> TdxLegacySubscriptionClient:
        return TdxLegacySubscriptionClient(
            adapter=adapter,
            bridge=bridge,
            collector=collector,
            max_subscriptions=settings.tdx.max_subscriptions,
        )

    async def _publish_collector_snapshot(self, snapshot: TdxSnapshot) -> None:
        await self.ws_manager.broadcast(
            ws_quote(provider="tdx", data=_serialize_snapshot_quote(snapshot))
        )

    async def health(self, *, instance: str = "tdx") -> dict[str, Any]:
        provider_health = await _tdx_provider_health(self.provider)
        bridge_health = _tdx_legacy_bridge_health(self.bridge)
        collector_health = _tdx_legacy_collector_health(self.collector)
        connection_count = _read_int(self.ws_manager, "connection_count", 0)
        return {
            "status": "ok",
            "instance": instance,
            "adapter": type(self.adapter).__name__ if self.adapter else "none",
            "connections": connection_count,
            "tdxHttpReachable": provider_health["tdxHttpReachable"],
            "tdxProviderError": provider_health.get("lastError")
            or provider_health.get("providerHealthError"),
            "tdxProviderErrorType": provider_health.get("providerHealthErrorType"),
            "tqInitialized": self.adapter is not None,
            "wsConnected": connection_count > 0,
            "subscribedCount": bridge_health["subscribedCount"],
            "activeSubscriptions": bridge_health["activeSubscriptions"],
            "lastCallbackAt": bridge_health["lastCallbackAt"],
            "quoteCallbackCount": bridge_health["quoteCallbackCount"],
            "quoteCallbackRejectedCount": bridge_health["quoteCallbackRejectedCount"],
            "lastQuoteCallbackAt": bridge_health["lastQuoteCallbackAt"],
            "lastQuoteCallbackCode": bridge_health["lastQuoteCallbackCode"],
            "lastQuoteCallbackSymbol": bridge_health["lastQuoteCallbackSymbol"],
            "lastQuoteCallbackAccepted": bridge_health["lastQuoteCallbackAccepted"],
            "lastQuoteCallbackRejectReason": bridge_health["lastQuoteCallbackRejectReason"],
            "lastMinuteBarAt": _prefer_collector_value(
                self.collector,
                collector_health["lastMinuteBarAt"],
                bridge_health["lastMinuteBarAt"],
            ),
            "eventQueueDepth": _prefer_collector_value(
                self.collector,
                collector_health["eventQueueDepth"],
                bridge_health["eventQueueDepth"],
            ),
            "eventQueueCapacity": _prefer_collector_value(
                self.collector,
                collector_health["eventQueueCapacity"],
                bridge_health["eventQueueCapacity"],
            ),
            "collectorState": collector_health["collectorState"],
        }


def _serialize_snapshot_quote(snapshot: TdxSnapshot) -> dict[str, Any]:
    return {
        "stock_code": snapshot.symbol,
        "snapshot": {
            "Code": snapshot.symbol,
            "Now": snapshot.last,
            "Open": snapshot.open,
            "High": snapshot.high,
            "Low": snapshot.low,
            "LastClose": snapshot.lastClose,
            "Volume": snapshot.volume,
            "Amount": snapshot.amount,
            "Provider": snapshot.provider,
            "AsOf": snapshot.asOf,
        },
    }


async def _tdx_provider_health(provider: Any | None) -> dict[str, Any]:
    if provider is None or not hasattr(provider, "health"):
        return {"tdxHttpReachable": False, "lastError": "TDX provider is not initialized"}

    try:
        health_status = await provider.health()
        if not isinstance(health_status, Mapping):
            return {
                "tdxHttpReachable": False,
                "providerHealthError": "TDX provider health returned a non-mapping payload",
                "providerHealthErrorType": type(health_status).__name__,
            }
        health_mapping = cast(Mapping[str, Any], health_status)
        return {
            "tdxHttpReachable": bool(health_mapping.get("tdxHttpReachable", False)),
            "lastError": health_mapping.get("lastError"),
        }
    except Exception as exc:
        return {
            "tdxHttpReachable": False,
            "providerHealthError": str(exc),
            "providerHealthErrorType": type(exc).__name__,
        }


def _tdx_legacy_bridge_health(bridge: Any | None) -> dict[str, Any]:
    if bridge is None:
        return {
            "subscribedCount": 0,
            "activeSubscriptions": [],
            "lastCallbackAt": None,
            "lastMinuteBarAt": None,
            "quoteCallbackCount": 0,
            "quoteCallbackRejectedCount": 0,
            "lastQuoteCallbackAt": None,
            "lastQuoteCallbackCode": None,
            "lastQuoteCallbackSymbol": None,
            "lastQuoteCallbackAccepted": None,
            "lastQuoteCallbackRejectReason": None,
            "eventQueueDepth": 0,
            "eventQueueCapacity": 0,
        }

    if hasattr(bridge, "health"):
        health_status = bridge.health()
        if isinstance(health_status, Mapping):
            bridge_health = cast(Mapping[str, Any], health_status)
            return {
                "subscribedCount": _read_mapping_int(bridge_health, "subscribed_count", 0),
                "activeSubscriptions": _read_mapping_list(
                    bridge_health,
                    "active_subscriptions",
                ),
                "lastCallbackAt": bridge_health.get("last_callback_at"),
                "lastMinuteBarAt": bridge_health.get("last_minute_bar_at"),
                "quoteCallbackCount": _read_mapping_int(
                    bridge_health,
                    "quote_callback_count",
                    0,
                ),
                "quoteCallbackRejectedCount": _read_mapping_int(
                    bridge_health,
                    "quote_callback_rejected_count",
                    0,
                ),
                "lastQuoteCallbackAt": bridge_health.get("last_quote_callback_at"),
                "lastQuoteCallbackCode": bridge_health.get("last_quote_callback_code"),
                "lastQuoteCallbackSymbol": bridge_health.get("last_quote_callback_symbol"),
                "lastQuoteCallbackAccepted": bridge_health.get("last_quote_callback_accepted"),
                "lastQuoteCallbackRejectReason": bridge_health.get(
                    "last_quote_callback_reject_reason"
                ),
                "eventQueueDepth": _read_mapping_int(bridge_health, "event_queue_depth", 0),
                "eventQueueCapacity": _read_mapping_int(
                    bridge_health,
                    "event_queue_capacity",
                    0,
                ),
            }

    return {
        "subscribedCount": _read_int(bridge, "subscribed_count", 0),
        "activeSubscriptions": _read_list(bridge, "active_subscriptions"),
        "lastCallbackAt": _read_attr(bridge, "last_callback_at", None),
        "lastMinuteBarAt": _read_attr(bridge, "last_minute_bar_at", None),
        "quoteCallbackCount": _read_int(bridge, "quote_callback_count", 0),
        "quoteCallbackRejectedCount": _read_int(
            bridge,
            "quote_callback_rejected_count",
            0,
        ),
        "lastQuoteCallbackAt": _read_attr(bridge, "last_quote_callback_at", None),
        "lastQuoteCallbackCode": _read_attr(bridge, "last_quote_callback_code", None),
        "lastQuoteCallbackSymbol": _read_attr(
            bridge,
            "last_quote_callback_symbol",
            None,
        ),
        "lastQuoteCallbackAccepted": _read_attr(
            bridge,
            "last_quote_callback_accepted",
            None,
        ),
        "lastQuoteCallbackRejectReason": _read_attr(
            bridge,
            "last_quote_callback_reject_reason",
            None,
        ),
        "eventQueueDepth": _read_int(bridge, "event_queue_depth", 0),
        "eventQueueCapacity": _read_int(bridge, "event_queue_capacity", 0),
    }


def _tdx_legacy_collector_health(collector: Any | None) -> dict[str, Any]:
    if collector is None:
        return {
            "lastMinuteBarAt": None,
            "eventQueueDepth": 0,
            "eventQueueCapacity": 0,
            "collectorState": "not_started",
        }

    return {
        "lastMinuteBarAt": _read_attr(collector, "last_minute_bar_at", None),
        "eventQueueDepth": _read_int(collector, "event_queue_depth", 0),
        "eventQueueCapacity": _read_int(collector, "event_queue_capacity", 0),
        "collectorState": _read_attr(collector, "state", "not_started"),
    }


def _prefer_collector_value(collector: Any | None, collector_value: Any, bridge_value: Any) -> Any:
    return bridge_value if collector is None else collector_value


def _read_attr(source: Any | None, name: str, default: Any) -> Any:
    if source is None:
        return default
    return getattr(source, name, default)


def _read_int(source: Any | None, name: str, default: int) -> int:
    value = _read_attr(source, name, default)
    return value if isinstance(value, int) else default


def _read_list(source: Any | None, name: str) -> list[Any]:
    value = _read_attr(source, name, [])
    return list(cast(list[Any] | tuple[Any, ...], value)) if isinstance(value, list | tuple) else []


def _read_mapping_int(source: Mapping[str, Any], name: str, default: int) -> int:
    value = source.get(name, default)
    return value if isinstance(value, int) else default


def _read_mapping_list(source: Mapping[str, Any], name: str) -> list[Any]:
    value = source.get(name, [])
    return list(cast(list[Any] | tuple[Any, ...], value)) if isinstance(value, list | tuple) else []
