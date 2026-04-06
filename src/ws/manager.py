"""WebSocket connection manager for NestJS backend connections."""

import asyncio

from fastapi import WebSocket

from src.ws.protocol import WSMessage


class ConnectionManager:
    """管理到 NestJS 的 WebSocket 连接.

    典型场景：1-2 个 NestJS 后端实例连接，不是面向终端用户.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept and register a WebSocket connection.

        Args:
            websocket: The WebSocket connection to accept
            client_id: Unique identifier for the client (e.g., NestJS instance ID)
        """
        await websocket.accept()
        async with self._lock:
            self._connections[client_id] = websocket

    async def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket connection.

        Args:
            client_id: The client ID to disconnect
        """
        async with self._lock:
            self._connections.pop(client_id, None)

    async def broadcast(self, message: WSMessage) -> None:
        """推送消息到所有连接的 NestJS 实例.

        Args:
            message: The WSMessage to broadcast
        """
        payload = message.to_json()
        dead: list[str] = []

        for cid, ws in self._connections.items():
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(cid)

        # Clean up dead connections
        for cid in dead:
            await self.disconnect(cid)

    async def send_to_client(self, client_id: str, message: WSMessage) -> bool:
        """Send a message to a specific client.

        Args:
            client_id: The target client ID
            message: The WSMessage to send

        Returns:
            True if the message was sent successfully, False otherwise
        """
        ws = self._connections.get(client_id)
        if ws:
            try:
                await ws.send_text(message.to_json())
                return True
            except Exception:
                await self.disconnect(client_id)
        return False

    @property
    def connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self._connections)

    @property
    def connected_clients(self) -> list[str]:
        """Get list of connected client IDs."""
        return list(self._connections.keys())
