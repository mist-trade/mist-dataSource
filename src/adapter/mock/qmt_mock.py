"""Mock QMT adapter for macOS development."""

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

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

    async def get_stock_list(self, market: str = "0") -> list[str]:
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

    async def get_stock_list_in_sector(self, block_code: str = "沪深300", block_type: int = 0, list_type: int = 0) -> list[str]:
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

    # Trading methods (mock implementations for testing)
    async def order_stock(
        self, stock_code: str, order_type: int, volume: int, price_type: int, price: float
    ) -> int:
        """Mock order placement."""
        return random.randint(100000, 999999)

    async def cancel_order_stock(self, order_id: int) -> int:
        """Mock order cancellation."""
        return 1

    async def query_stock_orders(self, order_id: int = 0) -> list[dict[str, Any]]:
        """Mock order query."""
        return []

    async def query_stock_positions(self) -> list[dict[str, Any]]:
        """Mock position query."""
        return []

    async def query_stock_asset(self) -> dict[str, Any]:
        """Mock asset query."""
        return {
            "cash": 1000000.0,
            "market_value": 500000.0,
            "total_asset": 1500000.0,
        }

    async def stock_account(self) -> dict[str, Any]:
        """Mock account query."""
        return {
            "account_id": self._account_id,
            "account_type": "stock",
        }

    async def query_positions(self) -> list[dict[str, Any]]:
        """Mock position query (alias for query_stock_positions)."""
        return await self.query_stock_positions()
