"""Base adapter abstract class for market data providers."""

from abc import ABC, abstractmethod


class MarketDataAdapter(ABC):
    """交易引擎适配器基类.

    仅定义 initialize/shutdown 抽象方法。
    TDX/QMT 各自在自己的 adapter 中定义全部方法，不共享签名。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """初始化连接."""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭连接."""
