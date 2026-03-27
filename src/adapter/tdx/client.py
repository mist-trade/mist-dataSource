"""TDX (TongDaXin) adapter implementation using tqcenter SDK.

Note: This module requires tqcenter SDK which is only available on Windows.
The通达信终端 must be running and logged in before using this adapter.
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
            # initialize 需要传入当前脚本路径
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

        Args:
            sector: 板块名称，默认 "通达信88"

        Returns:
            股票代码列表

        Raises:
            AdapterError: If the query fails
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
        dividend_type: str = "front",
    ) -> dict[str, Any]:
        """获取历史行情数据.

        Args:
            stock_list: 股票代码列表
            fields: 字段列表，如 ["Close", "Volume", "Open"]
            period: 周期，如 "1d", "1min", "5min", "15min", "30min", "60min"
            start_time: 开始时间，格式 "20240101"
            end_time: 结束时间，格式 "20241231"
            dividend_type: 复权类型，"front" 前复权，"none" 不复权

        Returns:
            行情数据字典，key 为字段名，value 为 {股票代码: 数据} 的字典

        Raises:
            AdapterError: If the query fails
        """
        try:
            df = self._tq.get_market_data(
                field_list=fields,
                stock_list=stock_list,
                start_time=start_time,
                end_time=end_time,
                dividend_type=dividend_type,
                period=period,
                fill_data=True,
            )
            # 使用 tq.price_df 提取各字段
            result = {}
            for field in fields:
                result[field] = self._tq.price_df(df, field, column_names=stock_list)
            return result
        except Exception as e:
            raise AdapterError(f"Failed to get market data: {e}") from e

    async def subscribe_quote(self, stock_list: list[str]) -> Any:
        """TDX 实时行情订阅.

        Note: TDX 实时行情推送机制需根据实际 API 实现.
        当前实现为占位符，需要根据 tqcenter 的实际 API 完善.

        Args:
            stock_list: 股票代码列表

        Raises:
            NotImplementedError: This feature is not yet implemented
        """
        raise NotImplementedError(
            "TDX real-time quote subscription is not yet implemented. "
            "Please refer to tqcenter documentation for the subscription API."
        )

    async def send_user_block(
        self, block_code: str, stocks: list[str]
    ) -> None:
        """发送自定义板块到通达信终端.

        Args:
            block_code: 板块代码，如 "BLOCK_MY"
            stocks: 股票代码列表

        Raises:
            AdapterError: If sending fails
        """
        try:
            self._tq.send_user_block(block_code, stocks, show=True)
        except Exception as e:
            raise AdapterError(f"Failed to send user block: {e}") from e
