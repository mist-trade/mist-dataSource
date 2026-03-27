"""Base adapter abstract class for market data providers."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class MarketDataAdapter(ABC):
    """交易引擎适配器基类."""

    @abstractmethod
    async def initialize(self) -> None:
        """初始化连接."""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭连接."""

    @abstractmethod
    async def get_stock_list(self, sector: str) -> list[str]:
        """获取板块股票列表.

        Args:
            sector: 板块名称，如 "通达信88"

        Returns:
            股票代码列表
        """

    @abstractmethod
    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str,
        start_time: str,
        end_time: str,
    ) -> dict[str, Any]:
        """获取历史行情数据.

        Args:
            stock_list: 股票代码列表
            fields: 字段列表，如 ["Close", "Volume"]
            period: 周期，如 "1d", "1min", "5min"
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            行情数据字典
        """

    @abstractmethod
    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        """订阅实时行情推送.

        Args:
            stock_list: 股票代码列表

        Yields:
            实时行情数据
        """
