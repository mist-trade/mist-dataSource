"""WebSocket message protocol definitions."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WSMessage(BaseModel):
    """WebSocket 消息标准格式."""

    type: Literal[
        "ready",
        "ping",
        "pong",
        "sync_subscriptions",
        "subscribe",
        "unsubscribe",
        "subscribed",
        "unsubscribed",
        "error",
        "tdx.experimental.snapshot",
        "qmt.experimental.snapshot",
        "stream_started",
    ]
    provider: str | None = None
    data: dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        """Convert message to JSON string."""
        return self.model_dump_json(exclude_none=True)


def ws_ready(provider: str, data: dict[str, Any]) -> WSMessage:
    """Create a ready message for a datasource WebSocket connection."""
    return WSMessage(type="ready", provider=provider, data=data)


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


def ws_experimental_snapshot(provider: str, data: dict[str, Any]) -> WSMessage:
    """Create an isolated experimental realtime snapshot frame.

    The realtime consumers only listen for provider-specific snapshot types.
    """
    if provider == "qmt":
        return WSMessage(type="qmt.experimental.snapshot", provider=provider, data=data)
    return WSMessage(type="tdx.experimental.snapshot", provider=provider, data=data)


def ws_stream_started(provider: str, data: dict[str, Any]) -> WSMessage:
    """Create a stream_started control event (owner generation changed).

    Already-connected clients receive this; late-connecting clients recover the
    epoch via ``ready``.
    """
    return WSMessage(type="stream_started", provider=provider, data=data)
