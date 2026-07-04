"""Mock QMT adapter for macOS development."""

import asyncio
import random
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from src.adapter.base import MarketDataAdapter


class QMTMockAdapter(MarketDataAdapter):
    """macOS 开发环境 mock，不依赖本地 QMT 客户端。"""

    def __init__(self, path: str, account_id: str) -> None:
        self._path = path
        self._account_id = account_id

    async def initialize(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def get_stock_list(self, market: str = "0") -> list[str]:
        _ = market
        return [
            "000001.SZ",
            "600000.SH",
            "600519.SH",
            "601318.SH",
            "000002.SZ",
            "000858.SZ",
            "601398.SH",
            "600036.SH",
        ]

    async def get_stock_list_in_sector(self, block_code: str = "沪深300", block_type: int = 0, list_type: int = 0) -> list[str]:
        _ = (block_code, block_type, list_type)
        return [
            "000001.SZ",
            "600000.SH",
            "600519.SH",
            "601318.SH",
            "000002.SZ",
            "000858.SZ",
            "601398.SH",
            "600036.SH",
        ]

    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        _ = (period, start_time, end_time, kwargs)
        result: dict[str, Any] = {}
        for field in fields:
            result[field] = {
                code: round(random.uniform(10, 100), 2) for code in stock_list
            }
        return result

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict[str, Any]]:
        while True:
            yield {
                code: {
                    "lastPrice": round(random.uniform(10, 100), 2),
                    "volume": random.randint(100, 10000),
                    "amount": round(random.uniform(1000, 100000), 2),
                    "time": int(datetime.now().timestamp() * 1000),
                }
                for code in stock_list
            }
            await asyncio.sleep(1)

    # ---- 行情扩展接口 mock ----

    async def get_local_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        _ = (period, start_time, end_time, kwargs)
        result: dict[str, Any] = {}
        for field in fields:
            result[field] = {
                code: round(random.uniform(10, 100), 2) for code in stock_list
            }
        return result

    async def get_full_tick(self, code_list: list[str]) -> dict[str, Any]:
        return {
            code: {
                "lastPrice": round(random.uniform(10, 100), 2),
                "open": round(random.uniform(10, 100), 2),
                "high": round(random.uniform(10, 100), 2),
                "low": round(random.uniform(10, 100), 2),
                "volume": random.randint(1000, 100000),
                "amount": round(random.uniform(10000, 1000000), 2),
            }
            for code in code_list
        }

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
        _ = (period, fields, start_time, end_time, count, dividend_type)
        return {code: {"close": round(random.uniform(10, 100), 2)} for code in stock_list}

    async def get_divid_factors(
        self,
        stock_code: str,
        start_time: str = "",
        end_time: str = "",
    ) -> dict[str, Any]:
        _ = (stock_code, start_time, end_time)
        return {
            "interest": 0.1,
            "stockBonus": 0.0,
            "stockGift": 0.0,
            "allotNum": 0.0,
            "allotPrice": 0.0,
        }

    async def download_history_data(
        self,
        stock_code: str,
        period: str,
        start_time: str = "",
        end_time: str = "",
        incrementally: bool | None = None,
    ) -> None:
        pass

    async def download_history_data2(
        self,
        stock_list: list[str],
        period: str,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        pass

    async def get_trading_dates(
        self,
        market: str,
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
    ) -> list[str]:
        _ = (market, start_time, end_time, count)
        return ["20260102", "20260105", "20260106", "20260107", "20260108"]

    async def get_trading_calendar(
        self,
        market: str,
        start_time: str = "",
        end_time: str = "",
    ) -> list[str]:
        _ = (market, start_time, end_time)
        return ["20260102", "20260105", "20260106", "20260107", "20260108"]

    async def get_holidays(self) -> list[str]:
        return ["20260101", "20260129", "20260130", "20260131"]

    async def download_holiday_data(self) -> None:
        pass

    async def get_period_list(self) -> list[str]:
        return ["tick", "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1mon"]

    # ---- 合约信息接口 mock ----

    async def get_instrument_detail(
        self,
        stock_code: str,
        iscomplete: bool = False,
    ) -> dict[str, Any]:
        _ = iscomplete
        return {
            "ExchangeID": "SH",
            "InstrumentID": stock_code,
            "InstrumentName": "MockStock",
            "PreClose": round(random.uniform(10, 100), 2),
            "IsTrading": True,
        }

    async def get_instrument_type(self, stock_code: str) -> dict[str, bool]:
        _ = stock_code
        return {"index": False, "stock": True, "fund": False, "etf": False}

    # ---- 财务数据接口 mock ----

    async def get_financial_data(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        report_type: str = "report_time",
    ) -> dict[str, Any]:
        _ = (table_list, start_time, end_time, report_type)
        return {code: {} for code in stock_list}

    async def download_financial_data(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
    ) -> None:
        pass

    async def download_financial_data2(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        pass

    # ---- 板块管理接口 mock ----

    async def get_sector_list(self) -> list[str]:
        return ["沪深A股", "沪深300", "中证500", "创业板", "科创板"]

    async def download_sector_data(self) -> None:
        pass

    async def get_index_weight(self, index_code: str) -> dict[str, float]:
        _ = index_code
        return {"600000.SH": 0.05, "000001.SZ": 0.03, "600519.SH": 0.08}

    async def download_index_weight(self) -> None:
        pass

    async def create_sector_folder(
        self,
        parent_node: str,
        folder_name: str,
        overwrite: bool = True,
    ) -> str:
        _ = (parent_node, overwrite)
        return folder_name

    async def create_sector(
        self,
        parent_node: str = "",
        sector_name: str = "",
        overwrite: bool = True,
    ) -> str:
        _ = (parent_node, overwrite)
        return sector_name

    async def add_sector(self, sector_name: str, stock_list: list[str]) -> None:
        pass

    async def remove_stock_from_sector(self, sector_name: str, stock_list: list[str]) -> bool:
        _ = (sector_name, stock_list)
        return True

    async def remove_sector(self, sector_name: str) -> None:
        pass

    async def reset_sector(self, sector_name: str, stock_list: list[str]) -> bool:
        _ = (sector_name, stock_list)
        return True

    # ---- ETF/可转债接口 mock ----

    async def get_cb_info(self, stock_code: str) -> dict[str, Any]:
        return {"stock_code": stock_code, "bond_name": "MockCB", "convert_price": round(random.uniform(90, 110), 2)}

    async def download_cb_data(self) -> None:
        pass

    async def get_ipo_info(self, start_time: str = "", end_time: str = "") -> list[dict[str, Any]]:
        _ = (start_time, end_time)
        return []

    async def get_etf_info(self) -> dict[str, Any]:
        return {}

    async def download_etf_info(self) -> None:
        pass

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
        _ = (stock_code, order_type, volume, price_type, price, strategy_name, order_remark)
        return 1

    async def query_stock_orders(self) -> list[dict[str, Any]]:
        return []

    async def query_stock_positions(self) -> list[dict[str, Any]]:
        return []
