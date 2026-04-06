"""Mock TDX adapter for macOS development."""

import asyncio
import random
from datetime import datetime
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter


class TDXMockAdapter(MarketDataAdapter):
    """macOS 开发环境 mock，不依赖 tqcenter."""

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def get_stock_list(self, market: str = "0") -> list[str]:
        return ["SH000001", "SH600519", "SZ000001", "SH601318", "SZ000858"]

    async def get_stock_list_in_sector(self, block_code: str = "通达信88", block_type: int = 0, list_type: int = 0) -> list[str]:
        return ["SH000001", "SH600519", "SZ000001", "SH601318", "SZ000858"]

    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        result = {}
        for field in fields:
            result[field] = {
                code: round(random.uniform(10, 100), 2) for code in stock_list
            }
        return result

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        while True:
            yield {
                code: {
                    "price": round(random.uniform(10, 100), 2),
                    "volume": random.randint(100, 10000),
                    "time": datetime.now().isoformat(),
                }
                for code in stock_list
            }
            await asyncio.sleep(1)
