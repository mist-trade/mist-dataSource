"""Mock QMT adapter for macOS development."""

import asyncio
import random
from datetime import datetime
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter


class QMTMockAdapter(MarketDataAdapter):
    """macOS 开发环境 mock，不依赖 xtquant."""

    def __init__(self, path: str, account_id: str) -> None:
        self._path = path
        self._account_id = account_id

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def get_stock_list(self, sector: str = "沪深300") -> list[str]:
        return [
            "000001.SZ",
            "600000.SH",
            "600519.SH",
            "601318.SH",
            "000002.SZ",
            "000858.SZ",
            "601398.SH",
            "600036.SH",
        ]

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
                    "lastPrice": round(random.uniform(10, 100), 2),
                    "volume": random.randint(100, 10000),
                    "amount": round(random.uniform(1000, 100000), 2),
                    "time": int(datetime.now().timestamp() * 1000),
                }
                for code in stock_list
            }
            await asyncio.sleep(1)
