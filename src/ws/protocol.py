"""WebSocket message protocol definitions."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WSMessage(BaseModel):
    """WebSocket 消息标准格式."""

    type: Literal["quote", "trade", "order", "position", "heartbeat", "error"]
    data: dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())

    def to_json(self) -> str:
        """Convert message to JSON string."""
        return self.model_dump_json()
