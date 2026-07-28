"""WebSocket connection manager for NestJS backend connections."""

import asyncio

from fastapi import WebSocket

from src.ws.protocol import WSMessage


class ConnectionManager:
    """管理到 NestJS 的 WebSocket 连接.

    典型场景：1-2 个 NestJS 后端实例连接，不是面向终端用户.
    """

    def __init__(
        self,
        *,
        send_timeout_seconds: float = 5.0,
        max_concurrent_sends: int = 16,
    ) -> None:
        if send_timeout_seconds <= 0:
            raise ValueError("send_timeout_seconds must be positive")
        if max_concurrent_sends <= 0:
            raise ValueError("max_concurrent_sends must be positive")
        self._connections: dict[str, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._send_timeout_seconds = send_timeout_seconds
        self._max_concurrent_sends = max_concurrent_sends

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept and register a WebSocket connection.

        Args:
            websocket: The WebSocket connection to accept
            client_id: Unique identifier for the client (e.g., NestJS instance ID)
        """
        await websocket.accept()
        async with self._lock:
            self._connections[client_id] = websocket

    async def connect_unique(self, websocket: WebSocket, client_id: str) -> bool:
        """Accept and register a connection only when client_id is unused."""
        async with self._lock:
            if client_id in self._connections:
                return False
            await websocket.accept()
            self._connections[client_id] = websocket
            return True

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
        async with self._lock:
            connections = list(self._connections.items())
        semaphore = asyncio.Semaphore(self._max_concurrent_sends)

        async def send(cid: str, ws: WebSocket) -> tuple[str, WebSocket] | None:
            try:
                async with semaphore:
                    await asyncio.wait_for(
                        ws.send_text(payload),
                        timeout=self._send_timeout_seconds,
                    )
            except Exception:
                return cid, ws
            return None

        failed = [
            item
            for item in await asyncio.gather(
                *(send(cid, ws) for cid, ws in connections)
            )
            if item is not None
        ]
        if failed:
            async with self._lock:
                for cid, ws in failed:
                    if self._connections.get(cid) is ws:
                        self._connections.pop(cid, None)

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
