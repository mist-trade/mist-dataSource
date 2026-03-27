"""Mock QMT adapter for macOS development."""

import asyncio
import random
from datetime import datetime
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter


class QMTMockAdapter(MarketDataAdapter):
    """macOS 开发环境 mock，不依赖 xtquant."""

    def __init__(self, path: str, account_id: str) -> None:
        """Initialize the QMT mock adapter.

        Args:
            path: QMT 客户端路径（ignored in mock）
            account_id: 账户 ID（ignored in mock）
        """
        self._path = path
        self._account_id = account_id

    async def initialize(self) -> None:
        """Initialize the mock adapter."""
        # No initialization needed for mock

    async def shutdown(self) -> None:
        """Shutdown the mock adapter."""
        # No cleanup needed for mock

    async def get_stock_list(self, sector: str = "沪深300") -> list[str]:
        """获取板块股票列表.

        Args:
            sector: 板块名称（ignored in mock）

        Returns:
            Mock 股票代码列表
        """
        return ["SH000300", "SH600000", "SZ000001", "SH601318", "SZ000002"]

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

    # ---- 交易接口 Mock (QMT 独有) ----

    async def order_stock(
        self,
        stock_code: str,
        order_type: int,
        order_volume: int,
        price_type: int,
        price: float = 0.0,
    ) -> int:
        """下单，返回订单 ID.

        Args:
            stock_code: 股票代码
            order_type: 订单类型
            order_volume: 委托数量
            price_type: 价格类型
            price: 委托价格

        Returns:
            Mock 订单 ID
        """
        return random.randint(100000, 999999)

    async def cancel_order(self, order_id: int) -> None:
        """撤单.

        Args:
            order_id: 订单 ID
        """
        # Mock: no-op

    async def query_positions(self) -> list[dict]:
        """查询持仓.

        Returns:
            Mock 持仓列表
        """
        return [
            {
                "stock_code": "SH600519",
                "volume": 100,
                "available_volume": 100,
                "price": 1800.0,
                "market_value": 180000.0,
            }
        ]

    async def query_orders(self) -> list[dict]:
        """查询当日委托.

        Returns:
            Mock 委托列表
        """
        return [
            {
                "order_id": 123456,
                "stock_code": "SH600519",
                "order_type": 0,
                "order_volume": 100,
                "price": 1800.0,
                "filled_volume": 0,
                "status": "已报",
            }
        ]
