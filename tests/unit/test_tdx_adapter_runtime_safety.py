import asyncio
import threading
import time
from typing import Any

import pytest

from src.adapter_legacy.tdx.client import TdxLegacyAdapter


class BlockingTq:
    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def get_stock_list(self, market: str) -> list[str]:
        self.calls.append(("get_stock_list", (market,), {}))
        self.release.wait(timeout=1)
        return ["600519.SH"]


@pytest.mark.asyncio
async def test_tdx_sdk_call_does_not_block_event_loop():
    tq = BlockingTq()
    adapter = TdxLegacyAdapter()
    adapter._tq = tq
    threading.Timer(0.2, tq.release.set).start()

    async def loop_tick() -> float:
        start = time.monotonic()
        await asyncio.sleep(0.02)
        return time.monotonic() - start

    stock_list_task = asyncio.create_task(adapter.get_stock_list("1"))
    tick_elapsed = await loop_tick()
    stock_list = await stock_list_task

    assert tick_elapsed < 0.1
    assert stock_list == ["600519.SH"]
    assert tq.calls == [("get_stock_list", ("1",), {})]
