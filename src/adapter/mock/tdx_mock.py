"""Mock TDX adapter for macOS development."""

import asyncio
import random
from datetime import datetime
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter


class TDXMockAdapter(MarketDataAdapter):
    """macOS 开发环境 mock，不依赖 tqcenter."""

    async def initialize(self) -> None:
        """Initialize the mock adapter."""
        # No initialization needed for mock

    async def shutdown(self) -> None:
        """Shutdown the mock adapter."""
        # No cleanup needed for mock

    async def get_stock_list(self, sector: str = "通达信88") -> list[str]:
        """获取板块股票列表.

        Args:
            sector: 板块名称（ignored in mock）

        Returns:
            Mock 股票代码列表
        """
        return ["SH000001", "SH600519", "SZ000001", "SH601318", "SZ000858"]

    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
    ) -> dict[str, Any]:
        """获取历史行情数据.

        Args:
            stock_list: 股票代码列表
            fields: 字段列表
            period: 周期（ignored in mock）
            start_time: 开始时间（ignored in mock）
            end_time: 结束时间（ignored in mock）

        Returns:
            Mock 行情数据
        """
        result = {}
        for field in fields:
            result[field] = {
                code: round(random.uniform(10, 100), 2) for code in stock_list
            }
        return result

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        """订阅实时行情推送.

        Args:
            stock_list: 股票代码列表

        Yields:
            模拟实时行情数据
        """
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
