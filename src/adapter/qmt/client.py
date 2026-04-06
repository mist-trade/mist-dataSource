"""QMT (miniQMT) adapter implementation using xtquant SDK.

Note: This module requires xtquant SDK which is only available on Windows.
The MiniQMT client must be running and logged in before using this adapter.

对应 QMT SDK: xtquant.xtdata (行情)

部署方式: 将 miniQMT 客户端的 Lib 目录路径设置为 QMT_SDK_PATH 环境变量,
例如: QMT_SDK_PATH=D:/miniQMT/Lib
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter
from src.core.config import settings
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
            # 将 SDK 路径添加到 sys.path, 使 xtquant 可被导入
            sdk_path = settings.qmt.sdk_path
            if sdk_path:
                sdk_dir = str(Path(sdk_path).resolve())
                if sdk_dir not in sys.path:
                    sys.path.insert(0, sdk_dir)

            from xtquant import xtdata

            self._xtdata = xtdata
            self._quote_queue = asyncio.Queue()

        except ImportError as e:
            raise ImportError(
                "xtquant SDK is not available. "
                "Please set QMT_SDK_PATH to the directory containing xtquant package "
                "(usually the Lib folder inside miniQMT installation). "
                "Use QMTMockAdapter for development on other platforms."
            ) from e
        except Exception as e:
            raise AdapterError(f"Failed to initialize QMT adapter: {e}") from e

    async def shutdown(self) -> None:
        """Shutdown QMT connection."""
        self._xtdata = None

    # ---- 行情接口 (xtdata) ----

    async def get_stock_list(self, market: str = "0") -> list[str]:
        """获取市场股票列表.

        对应 QMT SDK: xtdata.get_stock_list_in_sector(sector_name)
        """
        raise NotImplementedError("get_stock_list not implemented for QMT")

    async def get_stock_list_in_sector(self, block_code: str = "沪深300", block_type: int = 0, list_type: int = 0) -> list[str]:
        """获取板块股票列表.

        对应 QMT SDK: xtdata.get_stock_list_in_sector(sector_name)
        """
        try:
            if list_type == 0:
                return self._xtdata.get_stock_list_in_sector(block_code)
            else:
                # QMT doesn't support list_type=1 natively, return codes only
                return self._xtdata.get_stock_list_in_sector(block_code)
        except Exception as e:
            raise AdapterError(f"Failed to get stock list in sector: {e}") from e

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
