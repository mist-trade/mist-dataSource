"""In-memory WebSocket bridge state for the TDX datasource."""

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.datasource.contracts import BEIJING_TZ
from src.datasource.tdx_models import TdxBar
from src.datasource.tdx_normalization import dedupe_stable
from src.ws.protocol import ws_error, ws_ready


@dataclass(slots=True)
class SubscriptionPlan:
    to_subscribe: list[str] = field(default_factory=lambda: [])
    to_unsubscribe: list[str] = field(default_factory=lambda: [])
    desired: list[str] = field(default_factory=lambda: [])
    error_code: str | None = None
    error_message: str | None = None


class TdxBridge:
    """Runtime-only bridge state shared by TDX WebSocket connections."""

    def __init__(self, *, queue_max_size: int, max_subscriptions: int) -> None:
        self.leader_client_id: str | None = None
        self.connected_clients: set[str] = set()
        self.active_subscriptions: list[str] = []
        self.desired_subscriptions: list[str] = []
        self.subscription_state_known = False
        self.last_callback_at: str | None = None
        self.last_minute_bar_at: str | None = None
        self.last_quote_callback_at: str | None = None
        self.last_quote_callback_code: str | None = None
        self.last_quote_callback_symbol: str | None = None
        self.last_quote_callback_accepted: bool | None = None
        self.last_quote_callback_reject_reason: str | None = None
        self.quote_callback_count = 0
        self.quote_callback_rejected_count = 0
        self.event_queue_capacity = queue_max_size
        self.last_error_code: str | None = None
        self.dropped_event_count = 0
        self._max_subscriptions = max_subscriptions
        self._event_queue_depth = 0
        self._event_queue: deque[TdxBar] = deque(maxlen=queue_max_size)

    @property
    def event_queue_depth(self) -> int:
        return self._event_queue_depth

    @property
    def subscribed_count(self) -> int:
        return len(self.active_subscriptions)

    @property
    def max_subscriptions(self) -> int:
        return self._max_subscriptions

    def claim_leader(self, client_id: str) -> bool:
        self.connected_clients.add(client_id)
        if self.leader_client_id in (None, client_id):
            self.leader_client_id = client_id
            return True
        return False

    def disconnect(self, client_id: str) -> None:
        self.connected_clients.discard(client_id)
        if self.leader_client_id == client_id:
            self.leader_client_id = None
            self.desired_subscriptions = []
            self.active_subscriptions = []

    def plan_sync(self, symbols: Iterable[str]) -> SubscriptionPlan:
        desired = dedupe_stable(symbols)
        if len(desired) > self._max_subscriptions:
            self.last_error_code = "TDX_SUBSCRIBE_LIMIT_EXCEEDED"
            return SubscriptionPlan(
                desired=desired,
                error_code=self.last_error_code,
                error_message=f"Cannot subscribe to more than {self._max_subscriptions} symbols",
            )

        active = set(self.active_subscriptions)
        desired_set = set(desired)
        self.desired_subscriptions = desired
        self.last_error_code = None
        return SubscriptionPlan(
            to_subscribe=[symbol for symbol in desired if symbol not in active],
            to_unsubscribe=[
                symbol for symbol in self.active_subscriptions if symbol not in desired_set
            ],
            desired=desired,
        )

    def mark_active(self, symbols: Iterable[str]) -> None:
        self.active_subscriptions = dedupe_stable(symbols)
        self.subscription_state_known = True
        self.last_error_code = None

    def enqueue_bar(self, bar: TdxBar) -> bool:
        # Keep a bounded recent-events buffer for health/bookkeeping; publishing
        # happens separately and must not be blocked by an undrained buffer.
        self.record_callback(last_minute_bar_at=bar.barTime)
        dropped = False
        if len(self._event_queue) >= self.event_queue_capacity:
            self.dropped_event_count += 1
            self.report_backpressure()
            dropped = True
        self._event_queue.append(bar)
        self.record_queue_depth(len(self._event_queue))
        if not dropped:
            self.last_error_code = None
        return True

    def record_callback(self, last_minute_bar_at: str | None = None) -> None:
        self.last_callback_at = _now_beijing()
        if last_minute_bar_at is not None:
            self.last_minute_bar_at = last_minute_bar_at

    def record_quote_callback(
        self,
        *,
        code: str | None,
        normalized_symbol: str | None,
        accepted: bool,
        reject_reason: str | None,
    ) -> None:
        self.quote_callback_count += 1
        if not accepted:
            self.quote_callback_rejected_count += 1
        self.last_quote_callback_at = _now_beijing()
        self.last_quote_callback_code = code
        self.last_quote_callback_symbol = normalized_symbol
        self.last_quote_callback_accepted = accepted
        self.last_quote_callback_reject_reason = reject_reason

    def record_queue_depth(self, depth: int) -> None:
        self._event_queue_depth = max(0, depth)

    def report_backpressure(self) -> None:
        self.last_error_code = "DATASOURCE_WS_BACKPRESSURE"

    def health(self) -> dict[str, Any]:
        return {
            "subscribed_count": self.subscribed_count,
            "active_subscriptions": list(self.active_subscriptions),
            "last_callback_at": self.last_callback_at,
            "last_minute_bar_at": self.last_minute_bar_at,
            "quote_callback_count": self.quote_callback_count,
            "quote_callback_rejected_count": self.quote_callback_rejected_count,
            "last_quote_callback_at": self.last_quote_callback_at,
            "last_quote_callback_code": self.last_quote_callback_code,
            "last_quote_callback_symbol": self.last_quote_callback_symbol,
            "last_quote_callback_accepted": self.last_quote_callback_accepted,
            "last_quote_callback_reject_reason": self.last_quote_callback_reject_reason,
            "event_queue_depth": self.event_queue_depth,
            "event_queue_capacity": self.event_queue_capacity,
            "last_error_code": self.last_error_code,
            "dropped_event_count": self.dropped_event_count,
        }

    def make_ready_message(self) -> dict[str, Any]:
        return ws_ready(
            provider="tdx",
            data={
                "leaderClientId": self.leader_client_id,
                "active": list(self.active_subscriptions),
                "eventQueueDepth": self.event_queue_depth,
                "eventQueueCapacity": self.event_queue_capacity,
            },
        ).model_dump(exclude_none=True)

    def make_error_message(
        self,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.last_error_code = code
        return ws_error(
            provider="tdx",
            code=code,
            message=message,
            retryable=retryable,
            details=details,
        ).model_dump(exclude_none=True)


def _now_beijing() -> str:
    return datetime.now(BEIJING_TZ).isoformat()
