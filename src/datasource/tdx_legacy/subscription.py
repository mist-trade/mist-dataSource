"""Thin subscription wrapper around an initialized TDX adapter."""

import asyncio
import json
from collections.abc import Iterable
from contextlib import suppress
from typing import Any, cast

from src.core.config import settings
from src.core.logging import get_logger
from src.datasource.tdx_legacy.bridge import TdxLegacyBridge
from src.datasource.tdx_normalization import dedupe_normalized_symbols, normalize_symbol

TDX_SUBSCRIBE_LIMIT_EXCEEDED = "TDX_SUBSCRIBE_LIMIT_EXCEEDED"
logger = get_logger(__name__)


class TdxLegacySubscriptionClient:
    """Coordinate TDX SDK subscriptions without owning SDK initialization."""

    def __init__(
        self,
        *,
        adapter: Any,
        bridge: TdxLegacyBridge,
        collector: Any,
        max_subscriptions: int | None = None,
    ) -> None:
        self.adapter = adapter
        self.bridge = bridge
        self.collector = collector
        self.max_subscriptions = (
            settings.tdx.max_subscriptions if max_subscriptions is None else max_subscriptions
        )
        self._lock = asyncio.Lock()

    async def subscribe(self, symbols: Iterable[str]) -> dict[str, Any]:
        requested = dedupe_normalized_symbols(symbols)
        async with self._lock:
            desired = dedupe_normalized_symbols([*self.bridge.active_subscriptions, *requested])
            if len(desired) > self.max_subscriptions:
                self.bridge.last_error_code = TDX_SUBSCRIBE_LIMIT_EXCEEDED
                return {
                    "accepted": [],
                    "rejected": requested,
                    "active": list(self.bridge.active_subscriptions),
                    "error": _limit_error(self.max_subscriptions),
                }

            to_subscribe = [
                symbol
                for symbol in requested
                if symbol not in set(self.bridge.active_subscriptions)
            ]
            previous_active = list(self.bridge.active_subscriptions)
            try:
                if to_subscribe:
                    await self.adapter.subscribe_hq(to_subscribe, self._on_quote_update)
                self.bridge.mark_active(desired)
            except Exception:
                self.bridge.mark_active(previous_active)
                if to_subscribe:
                    with suppress(Exception):
                        await self.adapter.unsubscribe_hq(to_subscribe)
                if previous_active:
                    with suppress(Exception):
                        await self.adapter.subscribe_hq(previous_active, self._on_quote_update)
                raise

            return {
                "accepted": requested,
                "rejected": [],
                "active": list(self.bridge.active_subscriptions),
                "error": None,
            }

    async def sync(self, symbols: Iterable[str]) -> dict[str, Any]:
        desired = dedupe_normalized_symbols(symbols)
        async with self._lock:
            if len(desired) > self.max_subscriptions:
                self.bridge.last_error_code = TDX_SUBSCRIBE_LIMIT_EXCEEDED
                return {
                    "accepted": [],
                    "rejected": desired,
                    "active": list(self.bridge.active_subscriptions),
                    "error": _limit_error(self.max_subscriptions),
                }

            active = set(self.bridge.active_subscriptions)
            desired_set = set(desired)
            to_subscribe = [symbol for symbol in desired if symbol not in active]
            to_unsubscribe = [
                symbol for symbol in self.bridge.active_subscriptions if symbol not in desired_set
            ]
            previous_active = list(self.bridge.active_subscriptions)
            try:
                if to_unsubscribe:
                    await self.adapter.unsubscribe_hq(to_unsubscribe)
                if to_subscribe:
                    await self.adapter.subscribe_hq(to_subscribe, self._on_quote_update)
                self.bridge.mark_active(desired)
            except Exception:
                self.bridge.mark_active(previous_active)
                if to_subscribe:
                    with suppress(Exception):
                        await self.adapter.unsubscribe_hq(to_subscribe)
                if previous_active:
                    with suppress(Exception):
                        await self.adapter.subscribe_hq(
                            previous_active,
                            self._on_quote_update,
                        )
                raise

            return {
                "accepted": desired,
                "rejected": [],
                "active": list(self.bridge.active_subscriptions),
                "error": None,
            }

    async def unsubscribe(self, symbols: Iterable[str] | None = None) -> dict[str, Any]:
        async with self._lock:
            if symbols is None:
                to_unsubscribe = list(self.bridge.active_subscriptions)
                desired: list[str] = []
            else:
                requested = set(dedupe_normalized_symbols(symbols))
                to_unsubscribe = [
                    symbol for symbol in self.bridge.active_subscriptions if symbol in requested
                ]
                desired = [
                    symbol for symbol in self.bridge.active_subscriptions if symbol not in requested
                ]
            previous_active = list(self.bridge.active_subscriptions)

            try:
                if to_unsubscribe:
                    await self.adapter.unsubscribe_hq(to_unsubscribe)
                self.bridge.mark_active(desired)
            except Exception:
                self.bridge.mark_active(previous_active)
                if previous_active:
                    with suppress(Exception):
                        await self.adapter.subscribe_hq(previous_active, self._on_quote_update)
                raise

            return {
                "accepted": to_unsubscribe,
                "rejected": [],
                "active": list(self.bridge.active_subscriptions),
                "error": None,
            }

    def _on_quote_update(self, payload: Any) -> None:
        parsed_payload = _parse_quote_payload(payload)
        if parsed_payload is None:
            self.bridge.record_quote_callback(
                code=None,
                normalized_symbol=None,
                accepted=False,
                reject_reason="invalid_payload",
            )
            logger.warning(
                "TDX quote callback rejected reason=invalid_payload payload_type=%s",
                type(payload).__name__,
            )
            return

        payload = parsed_payload
        code = payload.get("Code")
        if not isinstance(code, str) or not code:
            self.bridge.record_quote_callback(
                code=None,
                normalized_symbol=None,
                accepted=False,
                reject_reason="missing_code",
            )
            logger.warning(
                "TDX quote callback rejected reason=missing_code payload_keys=%s",
                sorted(payload.keys()),
            )
            return
        normalized_symbol = normalize_symbol(code)
        active_subscriptions = set(self.bridge.active_subscriptions)
        if normalized_symbol not in active_subscriptions:
            self.bridge.record_quote_callback(
                code=code,
                normalized_symbol=normalized_symbol,
                accepted=False,
                reject_reason="inactive_subscription",
            )
            logger.warning(
                "TDX quote callback rejected reason=inactive_subscription "
                "code=%s symbol=%s active=%s error_id=%s",
                code,
                normalized_symbol,
                sorted(active_subscriptions),
                payload.get("ErrorId"),
            )
            return
        if self.collector is None:
            self.bridge.record_quote_callback(
                code=code,
                normalized_symbol=normalized_symbol,
                accepted=False,
                reject_reason="collector_unavailable",
            )
            logger.warning(
                "TDX quote callback rejected reason=collector_unavailable "
                "code=%s symbol=%s error_id=%s",
                code,
                normalized_symbol,
                payload.get("ErrorId"),
            )
            return

        self.bridge.record_quote_callback(
            code=code,
            normalized_symbol=normalized_symbol,
            accepted=True,
            reject_reason=None,
        )
        logger.info(
            "TDX quote callback accepted code=%s symbol=%s error_id=%s",
            code,
            normalized_symbol,
            payload.get("ErrorId"),
        )
        self.collector.mark_dirty_from_callback(payload)


def _parse_quote_payload(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)

    if isinstance(payload, bytes | bytearray):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return None

    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return cast(dict[str, Any], decoded) if isinstance(decoded, dict) else None

    return None


def _limit_error(max_subscriptions: int) -> dict[str, Any]:
    return {
        "code": TDX_SUBSCRIBE_LIMIT_EXCEEDED,
        "message": f"Cannot subscribe to more than {max_subscriptions} symbols",
        "retryable": False,
        "details": {"maxSubscriptions": max_subscriptions},
    }
