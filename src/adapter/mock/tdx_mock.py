"""Mock TDX adapter for macOS development with fixed deterministic data."""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from src.adapter.base import MarketDataAdapter


class TDXMockAdapter(MarketDataAdapter):
    """macOS 开发环境 mock，返回固定确定性的测试数据."""

    def __init__(self) -> None:
        self._fixtures_dir = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "tdx"
        self._subscribed_stocks: set[str] = set()
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """Load fixture data from JSON files."""
        self._snapshot = self._load_json("snapshot.json")
        self._financial = self._load_json("financial.json")
        self._sector_list = self._load_json("sector_list.json")
        self._kzz_info = self._load_json("kzz_info.json")
        self._trading_dates = self._load_json("trading_dates.json")

    def _load_json(self, filename: str) -> dict[str, Any]:
        """Load JSON fixture file."""
        path = self._fixtures_dir / filename
        if path.exists():
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        return {}

    async def initialize(self) -> None:
        """Initialize mock adapter."""
        pass

    async def shutdown(self) -> None:
        """Shutdown mock adapter."""
        self._subscribed_stocks.clear()

    # ---- Required Abstract Methods ----

    async def get_stock_list(self, market: str = "0") -> list[str]:
        """获取市场股票列表."""
        # Return fixed list of stocks
        return ["000001.SH", "600519.SH", "000001.SZ", "601318.SH", "000858.SZ"]

    async def get_stock_list_in_sector(
        self, block_code: str = "通达信88", block_type: int = 0, list_type: int = 0
    ) -> list[str]:
        """获取板块股票列表."""
        # Return fixed list of stocks for any sector
        return ["600519.SH", "000001.SZ", "601318.SH", "000858.SZ", "600036.SH"]

    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """获取历史行情数据."""
        result: dict[str, Any] = {}
        for field in fields:
            # Return fixed price data for each stock
            result[field] = {
                "600519.SH": [1750.00, 1755.00, 1748.00, 1752.00],
                "000001.SZ": [12.50, 12.55, 12.48, 12.52],
                "601318.SH": [45.20, 45.25, 45.18, 45.22],
                "000858.SZ": [85.30, 85.35, 85.28, 85.32],
                "600036.SH": [35.60, 35.65, 35.58, 35.62],
            }
            # Filter to requested stocks
            result[field] = {code: result[field].get(code, [100.0]) for code in stock_list}
        return result

    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        """订阅实时行情推送."""
        self._subscribed_stocks.update(stock_list)
        while True:
            # Return fixed quote data
            yield {
                code: {
                    "price": 1750.00 if code == "600519.SH" else 100.0,
                    "volume": 10000,
                    "time": datetime.now().isoformat(),
                }
                for code in stock_list
            }
            await asyncio.sleep(1)

    # ---- Market Data Methods ----

    async def get_market_snapshot(self, stock_code: str) -> dict[str, Any]:
        """获取市场快照数据."""
        # Return fixed snapshot data
        return self._snapshot.copy()

    async def get_full_tick(self, code_list: list[str]) -> dict[str, Any]:
        """获取全推数据（最新分笔快照）."""
        # Return fixed tick data for each code
        result = {}
        for code in code_list:
            result[code] = self._snapshot.copy()
        return result

    async def get_local_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """从本地数据文件获取行情数据."""
        return await self.get_market_data(stock_list, fields, period, start_time, end_time, **kwargs)

    async def get_full_kline(
        self, stock_list: list[str], period: str = "1m", fields: list[str] | None = None
    ) -> dict[str, Any]:
        """获取最新交易日K线全推数据."""
        if fields is None:
            fields = ["Open", "Close", "High", "Low", "Volume"]
        return await self.get_market_data(stock_list, fields, period)

    async def refresh_cache(self, stock_code: str) -> None:
        """刷新缓存数据."""
        pass

    async def refresh_kline(self, stock_code: str) -> None:
        """刷新K线数据."""
        pass

    async def download_file(self, file_type: str, stock_code: str = "") -> None:
        """下载文件数据."""
        pass

    # ---- Stock Info Methods ----

    async def get_instrument_detail(self, stock_code: str) -> dict[str, Any] | None:
        """获取合约基础信息."""
        # Return fixed instrument detail
        return {
            "Code": stock_code,
            "Name": "测试股票",
            "Market": "SH" if stock_code.endswith(".SH") else "SZ",
            "Type": "stock",
            "Status": "active",
        }

    async def get_instrument_type(self, stock_code: str) -> dict[str, bool] | None:
        """获取合约类型."""
        return {
            "stock": True,
            "fund": False,
            "index": False,
            "bond": False,
            "futures": False,
        }

    async def get_stock_info(self, stock_code: str) -> dict[str, Any]:
        """获取股票信息."""
        return {
            "Code": stock_code,
            "Name": "贵州茅台" if stock_code == "600519.SH" else "测试股票",
            "Market": "SH" if stock_code.endswith(".SH") else "SZ",
            "Industry": "白酒",
            "ListDate": "20010827",
            "TotalShare": 125619.78,
            "FlowShare": 125619.78,
        }

    async def get_report_data(self, stock_code: str) -> dict[str, Any]:
        """获取报告数据."""
        return {
            "Code": stock_code,
            "Name": "测试股票",
            "Open": 1750.00,
            "Close": 1752.00,
            "High": 1755.00,
            "Low": 1748.00,
            "Volume": 25000,
            "Amount": 438000000.00,
            "Tick": 0.02,
            "Change": 2.00,
            "ChangePct": 0.11,
            "Turnover": 0.20,
            "PE": 35.5,
            "PB": 12.3,
        }

    async def get_more_info(self, stock_code: str) -> dict[str, Any]:
        """获取更多信息."""
        return {
            "Code": stock_code,
            "Name": "测试股票",
            "Industry": "白酒",
            "Concept": ["贵州板块", "白酒", "MSCI中国"],
            "Area": "贵州",
        }

    async def get_relation(self, stock_code: str) -> dict[str, Any]:
        """获取关联信息."""
        return {
            "Code": stock_code,
            "RelatedStocks": ["000858.SZ", "600036.SH"],
            "RelatedSectors": ["880201.SH", "880207.SH"],
        }

    async def get_divid_factors(
        self, stock_code: str, start_time: str = "", end_time: str = ""
    ) -> dict[str, Any]:
        """获取除权数据."""
        return {
            "Code": stock_code,
            "Factors": [
                {"Date": "20240601", "Ratio": 1.1, "Bonus": 10.0},
                {"Date": "20230601", "Ratio": 1.0, "Bonus": 20.0},
            ],
        }

    async def download_history_data(
        self, stock_code: str, period: str, start_time: str = "", end_time: str = ""
    ) -> None:
        """补充历史行情数据."""
        pass

    async def download_history_data2(
        self, stock_list: list[str], period: str, start_time: str = "", end_time: str = ""
    ) -> None:
        """批量补充历史行情数据."""
        pass

    async def get_gb_info(self, stock_code: str) -> dict[str, Any]:
        """获取股本信息."""
        return {
            "Code": stock_code,
            "TotalShare": 125619.78,
            "FlowShare": 125619.78,
            "LimitedShare": 0.0,
        }

    # ---- Financial Methods ----

    async def get_financial_data(
        self,
        stock_list: list[str],
        field_list: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        report_type: str = "announce_time",
    ) -> dict[str, Any]:
        """获取财务数据."""
        # Return fixed financial data from fixture
        result = {}
        for code in stock_list:
            if code in self._financial:
                result[code] = self._financial[code]
            else:
                result[code] = {
                    "FN193": 15.23,
                    "FN194": 45.67,
                    "FN195": 123.45,
                    "FN196": 789.01,
                    "FN197": 2345.67,
                    "announce_time": "20250331",
                    "tag_time": "20241231",
                }
        return result

    async def download_financial_data(
        self, stock_list: list[str], field_list: list[str] | None = None
    ) -> None:
        """下载财务数据."""
        pass

    async def get_financial_data_by_date(
        self,
        stock_list: list[str],
        field_list: list[str],
        date: str,
        report_type: str = "announce_time",
    ) -> dict[str, Any]:
        """获取指定日期财务数据."""
        return await self.get_financial_data(stock_list, field_list, date, date, report_type)

    async def get_gp_one_data(
        self, stock_list: list[str], fields: list[str]
    ) -> dict[str, Any]:
        """获取股票一级数据."""
        result = {}
        for field in fields:
            result[field] = {
                code: 100.0 + hash(code + field) % 50 for code in stock_list
            }
        return result

    # ---- Value Methods ----

    async def get_bkjy_value(self, stock_list: list[str], fields: list[str]) -> dict[str, Any]:
        """获取板块交易数据."""
        result = {}
        for field in fields:
            result[field] = {code: 1000000.0 for code in stock_list}
        return result

    async def get_bkjy_value_by_date(
        self, stock_list: list[str], fields: list[str], date: str
    ) -> dict[str, Any]:
        """获取指定日期板块交易数据."""
        return await self.get_bkjy_value(stock_list, fields)

    async def get_gpjy_value(self, stock_list: list[str], fields: list[str]) -> dict[str, Any]:
        """获取股票交易数据."""
        result = {}
        for field in fields:
            result[field] = {code: 500000.0 for code in stock_list}
        return result

    async def get_gpjy_value_by_date(
        self, stock_list: list[str], fields: list[str], date: str
    ) -> dict[str, Any]:
        """获取指定日期股票交易数据."""
        return await self.get_gpjy_value(stock_list, fields)

    async def get_scjy_value(self, stock_list: list[str], fields: list[str]) -> dict[str, Any]:
        """获取市场交易数据."""
        result = {}
        for field in fields:
            result[field] = {code: 10000000.0 for code in stock_list}
        return result

    async def get_scjy_value_by_date(
        self, stock_list: list[str], fields: list[str], date: str
    ) -> dict[str, Any]:
        """获取指定日期市场交易数据."""
        return await self.get_scjy_value(stock_list, fields)

    # ---- Sector Methods ----

    async def get_sector_list(self, list_type: int = 0) -> list[str]:
        """获取板块列表."""
        return self._sector_list.get("codes_only", [])

    async def download_sector_data(self) -> None:
        """下载板块分类信息."""
        pass

    async def get_index_weight(self, index_code: str) -> dict[str, Any]:
        """获取指数成分权重信息."""
        return {
            "600519.SH": 15.23,
            "601318.SH": 8.45,
            "000001.SZ": 5.67,
            "000858.SZ": 3.21,
            "600036.SH": 2.89,
        }

    async def download_index_weight(self) -> None:
        """下载指数成分权重信息."""
        pass

    async def get_user_sector(self, name: str) -> list[str]:
        """获取自定义板块."""
        # Return fixed user sector stocks
        return ["600519.SH", "000001.SZ", "601318.SH"]

    async def create_sector(self, name: str, stocks: list[str]) -> None:
        """创建自定义板块."""
        pass

    async def delete_sector(self, name: str) -> None:
        """删除自定义板块."""
        pass

    async def rename_sector(self, old_name: str, new_name: str) -> None:
        """重命名自定义板块."""
        pass

    async def clear_sector(self, name: str) -> None:
        """清空自定义板块."""
        pass

    async def send_user_block(self, block_code: str, stocks: list[str]) -> None:
        """发送自定义板块到通达信终端."""
        pass

    # ---- ETF Methods ----

    async def get_kzz_info(self) -> dict[str, Any]:
        """获取可转债信息."""
        return self._kzz_info.copy()

    async def get_ipo_info(self) -> dict[str, Any]:
        """获取新股信息."""
        return {
            "IPOStocks": [
                {"Code": "301001.SZ", "Name": "新股1", "Date": "20250101", "Price": 25.50},
                {"Code": "301002.SZ", "Name": "新股2", "Date": "20250102", "Price": 30.00},
            ]
        }

    async def get_trackzs_etf_info(self) -> dict[str, Any]:
        """获取ETF跟踪指数信息."""
        return {
            "ETFs": [
                {"Code": "510300.SH", "Name": "沪深300ETF", "Index": "000300.SH"},
                {"Code": "510500.SH", "Name": "中证500ETF", "Index": "000905.SH"},
            ]
        }

    # ---- Subscription Methods ----

    async def subscribe_hq(self, stock_list: list[str]) -> None:
        """订阅行情."""
        self._subscribed_stocks.update(stock_list)

    async def unsubscribe_hq(self, stock_list: list[str]) -> None:
        """取消订阅行情."""
        for code in stock_list:
            self._subscribed_stocks.discard(code)

    async def get_subscribe_list(self) -> list[str]:
        """获取订阅列表."""
        return list(self._subscribed_stocks)

    async def subscribe_whole_quote(self, code_list: list[str]) -> AsyncIterator[dict]:
        """订阅全推行情数据."""
        while True:
            yield {code: self._snapshot.copy() for code in code_list}
            await asyncio.sleep(1)

    # ---- Trading Methods ----

    async def order_stock(
        self, stock_code: str, order_type: int, volume: int, price_type: int, price: float
    ) -> int:
        """下单."""
        return 123456

    async def cancel_order_stock(self, order_id: int) -> int:
        """撤单."""
        return 0

    async def query_stock_orders(self, order_id: int = 0) -> list[dict[str, Any]]:
        """查委托."""
        return [
            {
                "OrderID": 123456,
                "Code": "600519.SH",
                "Type": 1,
                "Volume": 100,
                "Price": 1750.00,
                "Status": "已成交",
            }
        ]

    async def query_stock_positions(self) -> list[dict[str, Any]]:
        """查持仓."""
        return [
            {
                "Code": "600519.SH",
                "Volume": 1000,
                "AvailVolume": 1000,
                "Cost": 1700.00,
                "Price": 1750.00,
                "Profit": 50000.00,
            }
        ]

    async def query_stock_asset(self) -> dict[str, Any]:
        """查资金."""
        return {
            "TotalAsset": 5000000.00,
            "Cash": 1000000.00,
            "MarketValue": 4000000.00,
            "Profit": 500000.00,
        }

    async def stock_account(self) -> dict[str, Any]:
        """查询账户信息."""
        return {
            "AccountID": "12345678",
            "AccountName": "测试账户",
            "AccountType": "普通账户",
        }

    # ---- Formula Methods ----

    async def formula_format_data(self, data: str) -> dict[str, Any]:
        """格式化公式数据."""
        return {"formatted": data, "status": "success"}

    async def formula_set_data(self, name: str, data: str) -> None:
        """设置公式数据."""
        pass

    async def formula_set_data_info(self, name: str, info: dict[str, Any]) -> None:
        """设置公式数据信息."""
        pass

    async def formula_get_data(self, name: str) -> dict[str, Any]:
        """获取公式数据."""
        return {"name": name, "data": "test_data"}

    async def formula_zb(self, formula: str, params: list[Any] | None = None) -> dict[str, Any]:
        """执行公式指标."""
        return {"formula": formula, "result": [1, 2, 3, 4, 5]}

    async def formula_exp(self, formula: str) -> dict[str, Any]:
        """执行公式表达式."""
        return {"formula": formula, "value": 42.0}

    async def formula_xg(self, formula: str) -> list[str]:
        """执行公式选股."""
        return ["600519.SH", "000001.SZ", "601318.SH"]

    async def formula_process(self, formula: str, stock_code: str) -> dict[str, Any]:
        """执行公式处理."""
        return {"formula": formula, "stock": stock_code, "result": "success"}

    async def formula_process_mul_xg(
        self, formulas: list[str], stock_list: list[str]
    ) -> dict[str, list[str]]:
        """执行多公式选股."""
        return {formula: ["600519.SH", "000001.SZ"] for formula in formulas}

    async def formula_process_mul_zb(
        self, formulas: list[str], stock_list: list[str]
    ) -> dict[str, Any]:
        """执行多公式指标."""
        return {
            formula: {stock: [1, 2, 3, 4, 5] for stock in stock_list}
            for formula in formulas
        }

    # ---- Client Communication Methods ----

    async def send_message(self, message: str) -> None:
        """发送消息."""
        pass

    async def send_file(self, file_path: str) -> None:
        """发送文件."""
        pass

    async def send_warn(self, message: str) -> None:
        """发送警告."""
        pass

    async def send_bt_data(self, data: dict[str, Any]) -> None:
        """发送回测数据."""
        pass

    async def print_to_tdx(self, message: str) -> None:
        """打印到通达信终端."""
        pass

    async def exec_to_tdx(self, code: str) -> None:
        """执行代码到通达信终端."""
        pass

    # ---- Trading Calendar & Holidays ----

    async def get_trading_dates(
        self, market: str, start_time: str = "", end_time: str = "", count: int = -1
    ) -> list[str]:
        """获取交易日列表."""
        dates = self._trading_dates.get("dates", [])
        if count > 0:
            return dates[:count]
        return dates

    async def get_trading_calendar(
        self, market: str, start_time: str = "", end_time: str = ""
    ) -> list[str]:
        """获取交易日历."""
        return self._trading_dates.get("dates", [])

    async def get_holidays(self) -> list[str]:
        """获取节假日数据."""
        return ["20250101", "20250128", "20250129", "20250130", "20250131"]

    async def download_holiday_data(self) -> None:
        """下载节假日数据."""
        pass
