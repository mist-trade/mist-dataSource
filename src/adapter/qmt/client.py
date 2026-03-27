"""QMT (miniQMT) adapter implementation using xtquant SDK.

Note: This module requires xtquant SDK which is only available on Windows.
The MiniQMT client must be running and logged in before using this adapter.
"""

from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter
from src.core.exceptions import AdapterError


class QMTCallback:
    """QMT 交易回调处理器.

    Note: This is a placeholder for the actual XtQuantTraderCallback.
    The actual implementation should inherit from xtquant.xttrader.XtQuantTraderCallback
    when running on Windows with xtquant installed.
    """

    def on_stock_order(self, order: Any) -> None:
        """订单状态变更回调.

        Args:
            order: 订单信息
        """
        # TODO: 通过 WebSocket 推送到 NestJS
        pass

    def on_stock_trade(self, trade: Any) -> None:
        """成交回报回调.

        Args:
            trade: 成交信息
        """
        pass

    def on_order_error(self, order_error: Any) -> None:
        """下单错误回调.

        Args:
            order_error: 错误信息
        """
        pass

    def on_disconnected(self) -> None:
        """连接断开回调."""
        pass


class QMTAdapter(MarketDataAdapter):
    """miniQMT 适配器 - 基于 xtquant SDK.

    前置条件：MiniQMT 客户端已启动并登录.

    Args:
        path: QMT 客户端安装路径
        account_id: QMT 资金账号

    Raises:
        ImportError: If xtquant is not available (non-Windows platforms)
        AdapterError: If QMT connection fails
    """

    def __init__(self, path: str, account_id: str) -> None:
        self._path = path
        self._account_id = account_id
        self._trader: Any = None
        self._account: Any = None
        self._callback: QMTCallback | None = None

    async def initialize(self) -> None:
        """Initialize QMT connection.

        Raises:
            ImportError: If xtquant SDK is not available
            AdapterError: If initialization fails
        """
        try:
            from xtquant.xttrader import XtQuantTrader, XtQuantTraderCallback
            from xtquant.xttype import StockAccount

            # Create actual callback with proper inheritance
            class ActualQMTCallback(XtQuantTraderCallback):
                def __init__(self, adapter: QMTAdapter) -> None:
                    self._adapter = adapter

                def on_stock_order(self, order: Any) -> None:
                    self._adapter._handle_order_event(order)

                def on_stock_trade(self, trade: Any) -> None:
                    self._adapter._handle_trade_event(trade)

                def on_order_error(self, order_error: Any) -> None:
                    self._adapter._handle_order_error(order_error)

                def on_disconnected(self) -> None:
                    self._adapter._handle_disconnected()

            self._trader = XtQuantTrader(self._path, self._account_id)
            self._account = StockAccount(self._account_id)
            self._callback = ActualQMTCallback(self)
            self._trader.register_callback(self._callback)
            self._trader.start()

            # 订阅账户信息
            self._trader.subscribe_account(self._account)

        except ImportError as e:
            raise ImportError(
                "xtquant SDK is not available. "
                "This adapter only works on Windows with QMT client installed. "
                "Use QMTMockAdapter for development on other platforms."
            ) from e
        except Exception as e:
            raise AdapterError(f"Failed to initialize QMT adapter: {e}") from e

    async def shutdown(self) -> None:
        """Shutdown QMT connection."""
        if self._trader:
            self._trader.stop()
            self._trader = None

    def _handle_order_event(self, order: Any) -> None:
        """Handle order event callback.

        Args:
            order: Order event data
        """
        # TODO: 通过 WebSocket 推送到 NestJS
        pass

    def _handle_trade_event(self, trade: Any) -> None:
        """Handle trade event callback.

        Args:
            trade: Trade event data
        """
        pass

    def _handle_order_error(self, order_error: Any) -> None:
        """Handle order error callback.

        Args:
            order_error: Error data
        """
        pass

    def _handle_disconnected(self) -> None:
        """Handle disconnection event."""
        pass

    async def get_stock_list(self, sector: str = "沪深300") -> list[str]:
        """获取板块股票列表.

        Args:
            sector: 板块名称

        Returns:
            股票代码列表

        Raises:
            AdapterError: If the query fails
        """
        try:
            from xtquant import xtdata

            return xtdata.get_stock_list_in_sector(sector)
        except Exception as e:
            raise AdapterError(f"Failed to get stock list: {e}") from e

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
            period: 周期
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            行情数据字典

        Raises:
            AdapterError: If the query fails
        """
        try:
            from xtquant import xtdata

            return xtdata.get_market_data(
                field_list=fields,
                stock_list=stock_list,
                period=period,
                start_time=start_time,
                end_time=end_time,
            )
        except Exception as e:
            raise AdapterError(f"Failed to get market data: {e}") from e

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        """订阅实时行情.

        Note: xtquant 使用回调模式，这里需要将回调转换为异步迭代器.
        实际实现需要使用 asyncio.Queue 来桥接回调和异步迭代.

        Args:
            stock_list: 股票代码列表

        Yields:
            实时行情数据

        Raises:
            NotImplementedError: This feature needs proper async implementation
        """
        # TODO: Implement proper async iterator with callback bridge
        raise NotImplementedError(
            "QMT real-time quote subscription requires async callback bridge implementation. "
            "This will be implemented in Phase 3."
        )

    # ---- 交易接口 (QMT 独有) ----

    async def order_stock(
        self,
        stock_code: str,
        order_type: int,
        order_volume: int,
        price_type: int,
        price: float = 0.0,
    ) -> int:
        """下单.

        Args:
            stock_code: 股票代码
            order_type: 订单类型（0=买，1=卖）
            order_volume: 委托数量
            price_type: 价格类型
            price: 委托价格

        Returns:
            订单 ID

        Raises:
            AdapterError: If order fails
        """
        if not self._trader:
            raise AdapterError("QMT trader not initialized")

        try:
            return self._trader.order_stock(
                self._account,
                stock_code,
                order_type,
                order_volume,
                price_type,
                price,
            )
        except Exception as e:
            raise AdapterError(f"Failed to place order: {e}") from e

    async def cancel_order(self, order_id: int) -> None:
        """撤单.

        Args:
            order_id: 订单 ID

        Raises:
            AdapterError: If cancellation fails
        """
        if not self._trader:
            raise AdapterError("QMT trader not initialized")

        try:
            self._trader.cancel_order_stock(self._account, order_id)
        except Exception as e:
            raise AdapterError(f"Failed to cancel order: {e}") from e

    async def query_positions(self) -> list:
        """查询持仓.

        Returns:
            持仓列表

        Raises:
            AdapterError: If query fails
        """
        if not self._trader:
            raise AdapterError("QMT trader not initialized")

        try:
            return self._trader.query_stock_positions(self._account)
        except Exception as e:
            raise AdapterError(f"Failed to query positions: {e}") from e

    async def query_orders(self) -> list:
        """查询当日委托.

        Returns:
            委托列表

        Raises:
            AdapterError: If query fails
        """
        if not self._trader:
            raise AdapterError("QMT trader not initialized")

        try:
            return self._trader.query_stock_orders(self._account)
        except Exception as e:
            raise AdapterError(f"Failed to query orders: {e}") from e
