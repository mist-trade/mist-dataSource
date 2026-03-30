"""QMT (miniQMT) adapter implementation using xtquant SDK.

Note: This module requires xtquant SDK which is only available on Windows.
The MiniQMT client must be running and logged in before using this adapter.

对应 QMT SDK: xtquant.xtdata (行情)
"""

import asyncio
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter
from src.core.exceptions import AdapterError


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
        self._xtdata: Any = None
        self._quote_queue: asyncio.Queue | None = None

    async def initialize(self) -> None:
        """Initialize QMT connection.

        Raises:
            ImportError: If xtquant SDK is not available
            AdapterError: If initialization fails
        """
        try:
            from xtquant import xtdata

            self._xtdata = xtdata
            self._quote_queue = asyncio.Queue()

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
        self._xtdata = None

    # ---- 行情接口 (xtdata) ----

    async def get_stock_list(self, sector: str = "沪深300") -> list[str]:
        """获取板块股票列表.

        对应 QMT SDK: xtdata.get_stock_list_in_sector(sector_name)
        """
        try:
            return self._xtdata.get_stock_list_in_sector(sector)
        except Exception as e:
            raise AdapterError(f"Failed to get stock list: {e}") from e

    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """获取历史行情数据.

        对应 QMT SDK: xtdata.get_market_data(
            field_list, stock_list, period, start_time, end_time,
            count, dividend_type, fill_data
        )

        支持的周期: tick, 1m, 5m, 15m, 30m, 1h, 1d, 1w, 1mon, 1q, 1hy, 1y
        支持的除权: none, front, back, front_ratio, back_ratio
        """
        try:
            dividend_type = kwargs.get("dividend_type", "none")
            count = kwargs.get("count", -1)
            fill_data = kwargs.get("fill_data", True)

            return self._xtdata.get_market_data(
                field_list=fields,
                stock_list=stock_list,
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=count,
                dividend_type=dividend_type,
                fill_data=fill_data,
            )
        except Exception as e:
            raise AdapterError(f"Failed to get market data: {e}") from e

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        """订阅单股实时行情.

        对应 QMT SDK: xtdata.subscribe_quote(stock_code, period, callback)

        使用 asyncio.Queue 桥接回调到异步迭代器.
        """
        if not self._quote_queue:
            self._quote_queue = asyncio.Queue()

        def _on_data(datas: dict) -> None:
            if self._quote_queue:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(self._quote_queue.put_nowait, datas)

        for stock_code in stock_list:
            self._xtdata.subscribe_quote(
                stock_code, period="tick", callback=_on_data
            )

        try:
            while True:
                data = await self._quote_queue.get()
                yield data
        finally:
            for stock_code in stock_list:
                self._xtdata.unsubscribe_quote(stock_code)
