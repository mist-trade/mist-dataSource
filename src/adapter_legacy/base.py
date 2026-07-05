"""Base adapter abstract class for market data providers."""

from abc import ABC, abstractmethod
from typing import Any, Protocol


class TdxLegacyAdapterBase(ABC):
    """交易引擎适配器基类.

    仅定义 initialize/shutdown 抽象方法。
    具体数据源在各自实现中定义方法，不共享签名。
    """

    @abstractmethod
    async def initialize(self) -> None:
        """初始化连接."""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭连接."""


class AdapterLifecycle(Protocol):
    async def initialize(self) -> None: ...

    async def shutdown(self) -> None: ...


class TdxLegacyAdapterProtocol(AdapterLifecycle, Protocol):
    async def get_stock_list_in_sector(
        self,
        block_code: str = "通达信88",
        block_type: int = 0,
        list_type: int = 0,
    ) -> list[str]: ...

    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def subscribe_hq(self, stock_list: list[str], callback: Any) -> Any: ...

    async def unsubscribe_hq(self, stock_list: list[str] | None = None) -> Any: ...
