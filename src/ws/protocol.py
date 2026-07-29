"""WebSocket message protocol definitions."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WSMessage(BaseModel):
    """WebSocket 消息标准格式."""

    type: Literal[
        "realtime.ready",
        "ping",
        "pong",
        "sync_subscriptions",
        "subscribe",
        "unsubscribe",
        "get_subscriptions",
        "subscriptions_synced",
        "subscribed",
        "unsubscribed",
        "subscriptions",
        "error",
        "realtime.native_snapshot",
    ]
    provider: str | None = None
    data: dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_json(self) -> str:
        """Convert message to JSON string."""
        return self.model_dump_json(exclude_none=True)


def ws_ready(provider: str, data: dict[str, Any]) -> WSMessage:
    """Create a ready message for a datasource WebSocket connection."""
    return WSMessage(type="realtime.ready", provider=provider, data=data)


def ws_pong(provider: str) -> WSMessage:
    """Create a heartbeat response message."""
    return WSMessage(type="pong", provider=provider, data={})


def ws_error(
    *,
    provider: str,
    code: str,
    message: str,
    retryable: bool,
    details: dict[str, Any] | None = None,
) -> WSMessage:
    """Create a machine-readable datasource WebSocket error."""
    return WSMessage(
        type="error",
        provider=provider,
        data={
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details or {},
        },
    )


def ws_subscription_ack(
    *,
    provider: str,
    msg_type: Literal["subscribed", "unsubscribed"],
    accepted: list[str],
    rejected: list[Any],
    active: list[str],
) -> WSMessage:
    """Create a canonical subscription acknowledgement message."""
    return WSMessage(
        type=msg_type,
        provider=provider,
        data={
            "accepted": accepted,
            "rejected": rejected,
            "active": active,
        },
    )


def ws_subscription_result(
    *,
    provider: str,
    msg_type: Literal[
        "subscriptions_synced",
        "subscribed",
        "unsubscribed",
        "subscriptions",
    ],
    data: dict[str, Any],
) -> WSMessage:
    """Create an exact success-or-failure subscription control response."""
    return WSMessage(type=msg_type, provider=provider, data=data)


def ws_realtime_snapshot(provider: str, data: dict[str, Any]) -> WSMessage:
    """Create a formal provider-native realtime snapshot frame."""
    return WSMessage(type="realtime.native_snapshot", provider=provider, data=data)
