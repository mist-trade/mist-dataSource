"""QMT (miniQMT) adapter implementation using xtquant SDK.

Note: This module requires xtquant SDK which is only available on Windows.
The MiniQMT client must be running and logged in before using this adapter.

对应 QMT SDK: xtquant.xtdata (行情)

部署方式: 将 miniQMT 客户端的 Lib 目录路径设置为 QMT_SDK_PATH 环境变量,
例如: QMT_PATH=F:/quant/qmt, QMT_SDK_PATH=F:/quant/qmt/Lib
"""

import asyncio
import importlib
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

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
        self._quote_queue: asyncio.Queue[dict[str, Any]] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

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

            self._xtdata = importlib.import_module("xtquant.xtdata")
            self._loop = asyncio.get_running_loop()
            self._quote_queue = asyncio.Queue[dict[str, Any]]()

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
        self._loop = None

    async def _call_xtdata(
        self,
        method_name: str,
        *args: Any,
        error_message: str | None = None,
        **kwargs: Any,
    ) -> Any:
        if self._xtdata is None:
            raise AdapterError("QMT adapter not initialized")
        method = getattr(self._xtdata, method_name)
        try:
            return await asyncio.to_thread(method, *args, **kwargs)
        except Exception as e:
            message = error_message or f"QMT SDK call {method_name} failed"
            raise AdapterError(f"{message}: {e}") from e

    # ---- 行情接口 (xtdata) ----

    async def get_stock_list(self, market: str = "0") -> list[str]:
        """获取市场股票列表.

        对应 QMT SDK: xtdata.get_stock_list_in_sector(sector_name)
        """
        raise NotImplementedError("get_stock_list not implemented for QMT")

    async def get_stock_list_in_sector(
        self, block_code: str = "沪深300", block_type: int = 0, list_type: int = 0
    ) -> list[str]:
        """获取板块股票列表.

        对应 QMT SDK: xtdata.get_stock_list_in_sector(sector_name)
        """
        _ = block_type
        try:
            # QMT doesn't support list_type variants natively; return codes only.
            _ = list_type
            return await self._call_xtdata("get_stock_list_in_sector", block_code)
        except AdapterError as e:
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

            return await self._call_xtdata(
                "get_market_data",
                field_list=fields,
                stock_list=stock_list,
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=count,
                dividend_type=dividend_type,
                fill_data=fill_data,
                error_message="Failed to get market data",
            )
        except AdapterError:
            raise

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict[str, Any]]:
        """订阅单股实时行情.

        对应 QMT SDK: xtdata.subscribe_quote(stock_code, period, callback)

        使用 asyncio.Queue 桥接回调到异步迭代器.
        """
        queue = self._quote_queue
        if queue is None:
            queue = asyncio.Queue[dict[str, Any]]()
            self._quote_queue = queue
        loop = asyncio.get_running_loop()
        self._loop = loop

        def _on_data(datas: dict[str, Any]) -> None:
            if not loop.is_closed():
                loop.call_soon_threadsafe(queue.put_nowait, datas)

        for stock_code in stock_list:
            await self._call_xtdata(
                "subscribe_quote",
                stock_code,
                period="tick",
                callback=_on_data,
                error_message="Failed to subscribe quote",
            )

        try:
            while True:
                data = await queue.get()
                yield data
        finally:
            for stock_code in stock_list:
                await self._call_xtdata(
                    "unsubscribe_quote",
                    stock_code,
                    error_message="Failed to unsubscribe quote",
                )

    # ---- 行情扩展接口 (xtdata) ----

    async def get_local_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            dividend_type = kwargs.get("dividend_type", "none")
            count = kwargs.get("count", -1)
            fill_data = kwargs.get("fill_data", True)
            return await self._call_xtdata(
                "get_local_data",
                field_list=fields,
                stock_list=stock_list,
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=count,
                dividend_type=dividend_type,
                fill_data=fill_data,
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to get local data: {e}") from e

    async def get_full_tick(self, code_list: list[str]) -> dict[str, Any]:
        try:
            return await self._call_xtdata("get_full_tick", code_list)
        except AdapterError as e:
            raise AdapterError(f"Failed to get full tick: {e}") from e

    async def get_full_kline(
        self,
        stock_list: list[str],
        period: str = "1m",
        fields: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        count: int = 1,
        dividend_type: str = "none",
    ) -> dict[str, Any]:
        try:
            return await self._call_xtdata(
                "get_full_kline",
                field_list=fields or [],
                stock_list=stock_list,
                period=period,
                start_time=start_time,
                end_time=end_time,
                count=count,
                dividend_type=dividend_type,
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to get full kline: {e}") from e

    async def get_divid_factors(
        self,
        stock_code: str,
        start_time: str = "",
        end_time: str = "",
    ) -> dict[str, Any]:
        try:
            return await self._call_xtdata("get_divid_factors", stock_code, start_time, end_time)
        except AdapterError as e:
            raise AdapterError(f"Failed to get divid factors: {e}") from e

    async def download_history_data(
        self,
        stock_code: str,
        period: str,
        start_time: str = "",
        end_time: str = "",
        incrementally: bool | None = None,
    ) -> None:
        try:
            await self._call_xtdata(
                "download_history_data",
                stock_code,
                period,
                start_time,
                end_time,
                incrementally,
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to download history data: {e}") from e

    async def download_history_data2(
        self,
        stock_list: list[str],
        period: str,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        try:
            await self._call_xtdata(
                "download_history_data2", stock_list, period, start_time, end_time
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to batch download history data: {e}") from e

    async def get_trading_dates(
        self,
        market: str,
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
    ) -> list[str]:
        try:
            return await self._call_xtdata("get_trading_dates", market, start_time, end_time, count)
        except AdapterError as e:
            raise AdapterError(f"Failed to get trading dates: {e}") from e

    async def get_trading_calendar(
        self,
        market: str,
        start_time: str = "",
        end_time: str = "",
    ) -> list[str]:
        try:
            return await self._call_xtdata("get_trading_calendar", market, start_time, end_time)
        except AdapterError as e:
            raise AdapterError(f"Failed to get trading calendar: {e}") from e

    async def get_holidays(self) -> list[str]:
        try:
            return await self._call_xtdata("get_holidays")
        except AdapterError as e:
            raise AdapterError(f"Failed to get holidays: {e}") from e

    async def download_holiday_data(self) -> None:
        try:
            await self._call_xtdata("download_holiday_data")
        except AdapterError as e:
            raise AdapterError(f"Failed to download holiday data: {e}") from e

    async def get_period_list(self) -> list[str]:
        try:
            return await self._call_xtdata("get_period_list")
        except AdapterError as e:
            raise AdapterError(f"Failed to get period list: {e}") from e

    # ---- 合约信息接口 (xtdata) ----

    async def get_instrument_detail(
        self,
        stock_code: str,
        iscomplete: bool = False,
    ) -> dict[str, Any] | None:
        try:
            return await self._call_xtdata("get_instrument_detail", stock_code, iscomplete)
        except AdapterError as e:
            raise AdapterError(f"Failed to get instrument detail: {e}") from e

    async def get_instrument_type(self, stock_code: str) -> dict[str, Any] | None:
        try:
            return await self._call_xtdata("get_instrument_type", stock_code)
        except AdapterError as e:
            raise AdapterError(f"Failed to get instrument type: {e}") from e

    # ---- 财务数据接口 (xtdata) ----

    async def get_financial_data(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        report_type: str = "report_time",
    ) -> dict[str, Any]:
        try:
            return await self._call_xtdata(
                "get_financial_data",
                stock_list,
                table_list or [],
                start_time,
                end_time,
                report_type,
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to get financial data: {e}") from e

    async def download_financial_data(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
    ) -> None:
        try:
            await self._call_xtdata("download_financial_data", stock_list, table_list or [])
        except AdapterError as e:
            raise AdapterError(f"Failed to download financial data: {e}") from e

    async def download_financial_data2(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        try:
            await self._call_xtdata(
                "download_financial_data2",
                stock_list,
                table_list or [],
                start_time,
                end_time,
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to batch download financial data: {e}") from e

    # ---- 板块管理接口 (xtdata) ----

    async def get_sector_list(self) -> list[str]:
        try:
            return await self._call_xtdata("get_sector_list")
        except AdapterError as e:
            raise AdapterError(f"Failed to get sector list: {e}") from e

    async def download_sector_data(self) -> None:
        try:
            await self._call_xtdata("download_sector_data")
        except AdapterError as e:
            raise AdapterError(f"Failed to download sector data: {e}") from e

    async def get_index_weight(self, index_code: str) -> dict[str, Any]:
        try:
            return await self._call_xtdata("get_index_weight", index_code)
        except AdapterError as e:
            raise AdapterError(f"Failed to get index weight: {e}") from e

    async def download_index_weight(self) -> None:
        try:
            await self._call_xtdata("download_index_weight")
        except AdapterError as e:
            raise AdapterError(f"Failed to download index weight: {e}") from e

    async def create_sector_folder(
        self,
        parent_node: str,
        folder_name: str,
        overwrite: bool = True,
    ) -> str:
        try:
            return await self._call_xtdata(
                "create_sector_folder", parent_node, folder_name, overwrite
            )
        except AdapterError as e:
            raise AdapterError(f"Failed to create sector folder: {e}") from e

    async def create_sector(
        self,
        parent_node: str = "",
        sector_name: str = "",
        overwrite: bool = True,
    ) -> str:
        try:
            return await self._call_xtdata("create_sector", parent_node, sector_name, overwrite)
        except AdapterError as e:
            raise AdapterError(f"Failed to create sector: {e}") from e

    async def add_sector(self, sector_name: str, stock_list: list[str]) -> None:
        try:
            await self._call_xtdata("add_sector", sector_name, stock_list)
        except AdapterError as e:
            raise AdapterError(f"Failed to add sector: {e}") from e

    async def remove_stock_from_sector(self, sector_name: str, stock_list: list[str]) -> bool:
        try:
            return await self._call_xtdata("remove_stock_from_sector", sector_name, stock_list)
        except AdapterError as e:
            raise AdapterError(f"Failed to remove stock from sector: {e}") from e

    async def remove_sector(self, sector_name: str) -> None:
        try:
            await self._call_xtdata("remove_sector", sector_name)
        except AdapterError as e:
            raise AdapterError(f"Failed to remove sector: {e}") from e

    async def reset_sector(self, sector_name: str, stock_list: list[str]) -> bool:
        try:
            return await self._call_xtdata("reset_sector", sector_name, stock_list)
        except AdapterError as e:
            raise AdapterError(f"Failed to reset sector: {e}") from e

    # ---- ETF/可转债接口 (xtdata) ----

    async def get_cb_info(self, stock_code: str) -> dict[str, Any]:
        try:
            return await self._call_xtdata("get_cb_info", stock_code)
        except AdapterError as e:
            raise AdapterError(f"Failed to get cb info: {e}") from e

    async def download_cb_data(self) -> None:
        try:
            await self._call_xtdata("download_cb_data")
        except AdapterError as e:
            raise AdapterError(f"Failed to download cb data: {e}") from e

    async def get_ipo_info(
        self,
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        try:
            return await self._call_xtdata("get_ipo_info", start_time, end_time)
        except AdapterError as e:
            raise AdapterError(f"Failed to get ipo info: {e}") from e

    async def get_etf_info(self) -> list[dict[str, Any]]:
        try:
            return await self._call_xtdata("get_etf_info")
        except AdapterError as e:
            raise AdapterError(f"Failed to get etf info: {e}") from e

    async def download_etf_info(self) -> None:
        try:
            await self._call_xtdata("download_etf_info")
        except AdapterError as e:
            raise AdapterError(f"Failed to download etf info: {e}") from e

    # ---- 交易存根 (XtTrader，待后续实现) ----

    async def order_stock(
        self,
        stock_code: str,
        order_type: int,
        volume: int,
        price_type: int,
        price: float,
        strategy_name: str = "",
        order_remark: str = "",
    ) -> int:
        raise NotImplementedError("order_stock not yet implemented")

    async def order_stock_async(
        self,
        stock_code: str,
        order_type: int,
        volume: int,
        price_type: int,
        price: float,
        strategy_name: str = "",
        order_remark: str = "",
    ) -> int:
        raise NotImplementedError("order_stock_async not yet implemented")

    async def cancel_order_stock(self, order_id: int) -> int:
        raise NotImplementedError("cancel_order_stock not yet implemented")

    async def cancel_order_stock_async(self, order_id: int) -> int:
        raise NotImplementedError("cancel_order_stock_async not yet implemented")

    async def query_stock_asset(self) -> dict[str, Any]:
        raise NotImplementedError("query_stock_asset not yet implemented")

    async def query_stock_orders(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_stock_orders not yet implemented")

    async def query_stock_order(self, order_id: int) -> dict[str, Any]:
        raise NotImplementedError("query_stock_order not yet implemented")

    async def query_stock_trades(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_stock_trades not yet implemented")

    async def query_stock_positions(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_stock_positions not yet implemented")

    async def query_stock_position(self, stock_code: str) -> dict[str, Any]:
        raise NotImplementedError("query_stock_position not yet implemented")

    async def fund_transfer(self, transfer_direction: int, price: float) -> int:
        raise NotImplementedError("fund_transfer not yet implemented")

    async def query_credit_detail(self) -> dict[str, Any]:
        raise NotImplementedError("query_credit_detail not yet implemented")

    async def query_stk_compacts(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_stk_compacts not yet implemented")

    async def query_credit_subjects(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_credit_subjects not yet implemented")

    async def query_credit_slo_code(self) -> list[str]:
        raise NotImplementedError("query_credit_slo_code not yet implemented")

    async def query_credit_assure(self) -> dict[str, Any]:
        raise NotImplementedError("query_credit_assure not yet implemented")

    async def query_account_infos(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_account_infos not yet implemented")

    async def query_account_status(self) -> dict[str, Any]:
        raise NotImplementedError("query_account_status not yet implemented")

    async def query_new_purchase_limit(self) -> dict[str, Any]:
        raise NotImplementedError("query_new_purchase_limit not yet implemented")

    async def query_ipo_data(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_ipo_data not yet implemented")

    async def query_com_fund(self) -> dict[str, Any]:
        raise NotImplementedError("query_com_fund not yet implemented")

    async def query_com_position(self) -> list[dict[str, Any]]:
        raise NotImplementedError("query_com_position not yet implemented")
