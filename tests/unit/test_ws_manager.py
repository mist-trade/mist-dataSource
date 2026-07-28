import asyncio
from typing import Any

import pytest

from src.ws.manager import ConnectionManager
from src.ws.protocol import WSMessage


class FakeWebSocket:
    def __init__(
        self,
        *,
        send_started: asyncio.Event | None = None,
        send_release: asyncio.Event | None = None,
        error: Exception | None = None,
    ) -> None:
        self.accepted = False
        self.messages: list[str] = []
        self.send_started = send_started
        self.send_release = send_release
        self.error = error

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, payload: str) -> None:
        if self.send_started is not None:
            self.send_started.set()
        if self.send_release is not None:
            await self.send_release.wait()
        if self.error is not None:
            raise self.error
        self.messages.append(payload)


def message() -> WSMessage:
    return WSMessage(type="ping", provider="tdx", data={})


@pytest.mark.asyncio
async def test_broadcast_timeout_does_not_block_healthy_connection() -> None:
    manager = ConnectionManager(send_timeout_seconds=0.01)
    blocked = FakeWebSocket(send_release=asyncio.Event())
    healthy = FakeWebSocket()
    await manager.connect(blocked, "blocked")
    await manager.connect(healthy, "healthy")

    await manager.broadcast(message())

    assert len(healthy.messages) == 1
    assert manager.connected_clients == ["healthy"]


@pytest.mark.asyncio
async def test_broadcast_failure_does_not_remove_replacement_connection() -> None:
    manager = ConnectionManager(send_timeout_seconds=1)
    send_started = asyncio.Event()
    send_release = asyncio.Event()
    original = FakeWebSocket(
        send_started=send_started,
        send_release=send_release,
        error=RuntimeError("send failed"),
    )
    replacement = FakeWebSocket()
    await manager.connect(original, "backend")

    broadcast = asyncio.create_task(manager.broadcast(message()))
    await send_started.wait()
    await manager.connect(replacement, "backend")
    send_release.set()
    await broadcast

    assert manager.connected_clients == ["backend"]
    assert manager._connections["backend"] is replacement


@pytest.mark.asyncio
async def test_broadcast_disconnect_during_send_does_not_mutate_iteration() -> None:
    manager = ConnectionManager(send_timeout_seconds=1)
    send_started = asyncio.Event()
    send_release = asyncio.Event()
    leaving = FakeWebSocket(send_started=send_started, send_release=send_release)
    healthy = FakeWebSocket()
    await manager.connect(leaving, "leaving")
    await manager.connect(healthy, "healthy")

    broadcast = asyncio.create_task(manager.broadcast(message()))
    await send_started.wait()
    await manager.disconnect("leaving")
    send_release.set()
    await broadcast

    assert len(healthy.messages) == 1
    assert manager.connected_clients == ["healthy"]


@pytest.mark.asyncio
async def test_broadcast_respects_concurrency_bound() -> None:
    active = 0
    maximum_active = 0
    release = asyncio.Event()

    class CountingWebSocket(FakeWebSocket):
        async def send_text(self, payload: str) -> None:
            nonlocal active, maximum_active
            active += 1
            maximum_active = max(maximum_active, active)
            await release.wait()
            self.messages.append(payload)
            active -= 1

    manager = ConnectionManager(
        send_timeout_seconds=1,
        max_concurrent_sends=2,
    )
    sockets: list[CountingWebSocket] = []
    for index in range(5):
        websocket = CountingWebSocket()
        sockets.append(websocket)
        await manager.connect(websocket, f"backend-{index}")

    broadcast = asyncio.create_task(manager.broadcast(message()))
    while maximum_active < 2:
        await asyncio.sleep(0)
    assert maximum_active == 2
    release.set()
    await broadcast

    assert all(len(websocket.messages) == 1 for websocket in sockets)


@pytest.mark.parametrize(
    ("kwargs", "message_text"),
    [
        ({"send_timeout_seconds": 0}, "send_timeout_seconds must be positive"),
        ({"max_concurrent_sends": 0}, "max_concurrent_sends must be positive"),
    ],
)
def test_manager_rejects_invalid_send_bounds(
    kwargs: dict[str, Any], message_text: str
) -> None:
    with pytest.raises(ValueError, match=message_text):
        ConnectionManager(**kwargs)
