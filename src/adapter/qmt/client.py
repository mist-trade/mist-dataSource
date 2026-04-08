"""QMT (miniQMT) adapter implementation using xtquant SDK.

Note: This module requires xtquant SDK which is only available on Windows.
The MiniQMT client must be running and logged in before using this adapter.

对应 QMT SDK: xtquant.xtdata (行情)

部署方式: 将 miniQMT 客户端的 Lib 目录路径设置为 QMT_SDK_PATH 环境变量,
例如: QMT_SDK_PATH=D:/miniQMT/Lib
"""

import asyncio
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

    # ---- 行情扩展接口 (xtdata) ----

    async def get_local_data(self, stock_list, fields, period="1d", start_time="", end_time="", **kwargs):
        try:
            dividend_type = kwargs.get("dividend_type", "none")
            count = kwargs.get("count", -1)
            fill_data = kwargs.get("fill_data", True)
            return self._xtdata.get_local_data(
                field_list=fields, stock_list=stock_list, period=period,
                start_time=start_time, end_time=end_time, count=count,
                dividend_type=dividend_type, fill_data=fill_data,
            )
        except Exception as e:
            raise AdapterError(f"Failed to get local data: {e}") from e

    async def get_full_tick(self, code_list: list[str]) -> dict[str, Any]:
        try:
            return self._xtdata.get_full_tick(code_list)
        except Exception as e:
            raise AdapterError(f"Failed to get full tick: {e}") from e

    async def get_full_kline(self, stock_list, period="1m", fields=None, start_time="", end_time="", count=1, dividend_type="none"):
        try:
            return self._xtdata.get_full_kline(
                field_list=fields or [], stock_list=stock_list, period=period,
                start_time=start_time, end_time=end_time, count=count,
                dividend_type=dividend_type,
            )
        except Exception as e:
            raise AdapterError(f"Failed to get full kline: {e}") from e

    async def get_divid_factors(self, stock_code, start_time="", end_time=""):
        try:
            return self._xtdata.get_divid_factors(stock_code, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get divid factors: {e}") from e

    async def download_history_data(self, stock_code, period, start_time="", end_time="", incrementally=None):
        try:
            self._xtdata.download_history_data(stock_code, period, start_time, end_time, incrementally)
        except Exception as e:
            raise AdapterError(f"Failed to download history data: {e}") from e

    async def download_history_data2(self, stock_list, period, start_time="", end_time=""):
        try:
            self._xtdata.download_history_data2(stock_list, period, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to batch download history data: {e}") from e

    async def get_trading_dates(self, market, start_time="", end_time="", count=-1):
        try:
            return self._xtdata.get_trading_dates(market, start_time, end_time, count)
        except Exception as e:
            raise AdapterError(f"Failed to get trading dates: {e}") from e

    async def get_trading_calendar(self, market, start_time="", end_time=""):
        try:
            return self._xtdata.get_trading_calendar(market, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get trading calendar: {e}") from e

    async def get_holidays(self):
        try:
            return self._xtdata.get_holidays()
        except Exception as e:
            raise AdapterError(f"Failed to get holidays: {e}") from e

    async def download_holiday_data(self):
        try:
            self._xtdata.download_holiday_data()
        except Exception as e:
            raise AdapterError(f"Failed to download holiday data: {e}") from e

    async def get_period_list(self):
        try:
            return self._xtdata.get_period_list()
        except Exception as e:
            raise AdapterError(f"Failed to get period list: {e}") from e

    # ---- 合约信息接口 (xtdata) ----

    async def get_instrument_detail(self, stock_code, iscomplete=False):
        try:
            return self._xtdata.get_instrument_detail(stock_code, iscomplete)
        except Exception as e:
            raise AdapterError(f"Failed to get instrument detail: {e}") from e

    async def get_instrument_type(self, stock_code):
        try:
            return self._xtdata.get_instrument_type(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get instrument type: {e}") from e

    # ---- 财务数据接口 (xtdata) ----

    async def get_financial_data(self, stock_list, table_list=None, start_time="", end_time="", report_type="report_time"):
        try:
            return self._xtdata.get_financial_data(stock_list, table_list or [], start_time, end_time, report_type)
        except Exception as e:
            raise AdapterError(f"Failed to get financial data: {e}") from e

    async def download_financial_data(self, stock_list, table_list=None):
        try:
            self._xtdata.download_financial_data(stock_list, table_list or [])
        except Exception as e:
            raise AdapterError(f"Failed to download financial data: {e}") from e

    async def download_financial_data2(self, stock_list, table_list=None, start_time="", end_time=""):
        try:
            self._xtdata.download_financial_data2(stock_list, table_list or [], start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to batch download financial data: {e}") from e

    # ---- 板块管理接口 (xtdata) ----

    async def get_sector_list(self):
        try:
            return self._xtdata.get_sector_list()
        except Exception as e:
            raise AdapterError(f"Failed to get sector list: {e}") from e

    async def download_sector_data(self):
        try:
            self._xtdata.download_sector_data()
        except Exception as e:
            raise AdapterError(f"Failed to download sector data: {e}") from e

    async def get_index_weight(self, index_code):
        try:
            return self._xtdata.get_index_weight(index_code)
        except Exception as e:
            raise AdapterError(f"Failed to get index weight: {e}") from e

    async def download_index_weight(self):
        try:
            self._xtdata.download_index_weight()
        except Exception as e:
            raise AdapterError(f"Failed to download index weight: {e}") from e

    async def create_sector_folder(self, parent_node, folder_name, overwrite=True):
        try:
            return self._xtdata.create_sector_folder(parent_node, folder_name, overwrite)
        except Exception as e:
            raise AdapterError(f"Failed to create sector folder: {e}") from e

    async def create_sector(self, parent_node="", sector_name="", overwrite=True):
        try:
            return self._xtdata.create_sector(parent_node, sector_name, overwrite)
        except Exception as e:
            raise AdapterError(f"Failed to create sector: {e}") from e

    async def add_sector(self, sector_name, stock_list):
        try:
            self._xtdata.add_sector(sector_name, stock_list)
        except Exception as e:
            raise AdapterError(f"Failed to add sector: {e}") from e

    async def remove_stock_from_sector(self, sector_name, stock_list):
        try:
            return self._xtdata.remove_stock_from_sector(sector_name, stock_list)
        except Exception as e:
            raise AdapterError(f"Failed to remove stock from sector: {e}") from e

    async def remove_sector(self, sector_name):
        try:
            self._xtdata.remove_sector(sector_name)
        except Exception as e:
            raise AdapterError(f"Failed to remove sector: {e}") from e

    async def reset_sector(self, sector_name, stock_list):
        try:
            return self._xtdata.reset_sector(sector_name, stock_list)
        except Exception as e:
            raise AdapterError(f"Failed to reset sector: {e}") from e

    # ---- ETF/可转债接口 (xtdata) ----

    async def get_cb_info(self, stock_code):
        try:
            return self._xtdata.get_cb_info(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get cb info: {e}") from e

    async def download_cb_data(self):
        try:
            self._xtdata.download_cb_data()
        except Exception as e:
            raise AdapterError(f"Failed to download cb data: {e}") from e

    async def get_ipo_info(self, start_time="", end_time=""):
        try:
            return self._xtdata.get_ipo_info(start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get ipo info: {e}") from e

    async def get_etf_info(self):
        try:
            return self._xtdata.get_etf_info()
        except Exception as e:
            raise AdapterError(f"Failed to get etf info: {e}") from e

    async def download_etf_info(self):
        try:
            self._xtdata.download_etf_info()
        except Exception as e:
            raise AdapterError(f"Failed to download etf info: {e}") from e

    # ---- 交易存根 (XtTrader，待后续实现) ----

    async def order_stock(self, stock_code, order_type, volume, price_type, price, strategy_name="", order_remark=""):
        raise NotImplementedError("order_stock not yet implemented")

    async def order_stock_async(self, stock_code, order_type, volume, price_type, price, strategy_name="", order_remark=""):
        raise NotImplementedError("order_stock_async not yet implemented")

    async def cancel_order_stock(self, order_id):
        raise NotImplementedError("cancel_order_stock not yet implemented")

    async def cancel_order_stock_async(self, order_id):
        raise NotImplementedError("cancel_order_stock_async not yet implemented")

    async def query_stock_asset(self):
        raise NotImplementedError("query_stock_asset not yet implemented")

    async def query_stock_orders(self):
        raise NotImplementedError("query_stock_orders not yet implemented")

    async def query_stock_order(self, order_id):
        raise NotImplementedError("query_stock_order not yet implemented")

    async def query_stock_trades(self):
        raise NotImplementedError("query_stock_trades not yet implemented")

    async def query_stock_positions(self):
        raise NotImplementedError("query_stock_positions not yet implemented")

    async def query_stock_position(self, stock_code):
        raise NotImplementedError("query_stock_position not yet implemented")

    async def fund_transfer(self, transfer_direction, price):
        raise NotImplementedError("fund_transfer not yet implemented")

    async def query_credit_detail(self):
        raise NotImplementedError("query_credit_detail not yet implemented")

    async def query_stk_compacts(self):
        raise NotImplementedError("query_stk_compacts not yet implemented")

    async def query_credit_subjects(self):
        raise NotImplementedError("query_credit_subjects not yet implemented")

    async def query_credit_slo_code(self):
        raise NotImplementedError("query_credit_slo_code not yet implemented")

    async def query_credit_assure(self):
        raise NotImplementedError("query_credit_assure not yet implemented")

    async def query_account_infos(self):
        raise NotImplementedError("query_account_infos not yet implemented")

    async def query_account_status(self):
        raise NotImplementedError("query_account_status not yet implemented")

    async def query_new_purchase_limit(self):
        raise NotImplementedError("query_new_purchase_limit not yet implemented")

    async def query_ipo_data(self):
        raise NotImplementedError("query_ipo_data not yet implemented")

    async def query_com_fund(self):
        raise NotImplementedError("query_com_fund not yet implemented")

    async def query_com_position(self):
        raise NotImplementedError("query_com_position not yet implemented")
