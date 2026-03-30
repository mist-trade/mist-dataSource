"""TDX (TongDaXin) adapter implementation using tqcenter SDK.

Note: This module requires tqcenter SDK which is only available on Windows.
The通达信终端 must be running and logged in before using this adapter.

对应 TDX SDK: tqcenter.tq
"""

import os
from typing import Any

from src.adapter.base import MarketDataAdapter
from src.core.exceptions import AdapterError


class TDXAdapter(MarketDataAdapter):
    """通达信适配器 - 基于 tqcenter SDK.

    前置条件：通达信终端已启动并登录.

    Raises:
        ImportError: If tqcenter is not available (non-Windows platforms)
        AdapterError: If TDX connection fails
    """

    def __init__(self) -> None:
        self._tq: Any = None

    async def initialize(self) -> None:
        """Initialize TDX connection.

        Raises:
            ImportError: If tqcenter SDK is not available
            AdapterError: If initialization fails
        """
        try:
            from tqcenter import tq

            self._tq = tq
            tq.initialize(os.path.abspath(__file__))
        except ImportError as e:
            raise ImportError(
                "tqcenter SDK is not available. "
                "This adapter only works on Windows with TDX client installed. "
                "Use TDXMockAdapter for development on other platforms."
            ) from e
        except Exception as e:
            raise AdapterError(f"Failed to initialize TDX adapter: {e}") from e

    async def shutdown(self) -> None:
        """Shutdown TDX connection."""
        self._tq = None

    async def get_stock_list(self, sector: str = "通达信88") -> list[str]:
        """获取板块股票列表.

        对应 TDX SDK: tq.get_stock_list_in_sector(sector)
        """
        try:
            return self._tq.get_stock_list_in_sector(sector)
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

        对应 TDX SDK: tq.get_market_data(
            field_list, stock_list, start_time, end_time,
            dividend_type, period, fill_data
        )

        支持的周期: 1d, 1m, 5m
        支持的除权: none, front, back
        """
        try:
            dividend_type = kwargs.get("dividend_type", "front")

            df = self._tq.get_market_data(
                field_list=fields,
                stock_list=stock_list,
                start_time=start_time,
                end_time=end_time,
                dividend_type=dividend_type,
                period=period,
                fill_data=True,
            )
            result = {}
            for field in fields:
                result[field] = self._tq.price_df(df, field, column_names=stock_list)
            return result
        except Exception as e:
            raise AdapterError(f"Failed to get market data: {e}") from e

    async def subscribe_quote(self, stock_list: list[str]) -> Any:
        """TDX 实时行情订阅.

        对应 TDX SDK: tq.subscribe_hq(stock_list, callback)

        Note: TDX 实时行情推送机制需根据实际 API 实现.
        """
        raise NotImplementedError(
            "TDX real-time quote subscription is not yet implemented. "
            "Please refer to tqcenter documentation for the subscription API."
        )

    async def send_user_block(
        self, block_code: str, stocks: list[str]
    ) -> None:
        """发送自定义板块到通达信终端.

        对应 TDX SDK: tq.send_user_block(block_code, stocks, show=True)
        """
        try:
            self._tq.send_user_block(block_code, stocks, show=True)
        except Exception as e:
            raise AdapterError(f"Failed to send user block: {e}") from e
