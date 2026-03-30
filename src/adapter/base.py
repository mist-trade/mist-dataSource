"""Base adapter abstract class for market data providers."""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class MarketDataAdapter(ABC):
    """交易引擎适配器基类."""

    @abstractmethod
    async def initialize(self) -> None:
        """初始化连接."""

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭连接."""

    @abstractmethod
    async def get_stock_list(self, sector: str) -> list[str]:
        """获取板块股票列表.

        Args:
            sector: 板块名称，如 "通达信88"

        Returns:
            股票代码列表
        """

    @abstractmethod
    async def get_market_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str,
        start_time: str,
        end_time: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """获取历史行情数据.

        Args:
            stock_list: 股票代码列表
            fields: 字段列表，如 ["Close", "Volume"]
            period: 周期，如 "1d", "1m", "5m"
            start_time: 开始时间
            end_time: 结束时间
            **kwargs: 额外参数（如 dividend_type, count, fill_data）

        Returns:
            行情数据字典
        """

    @abstractmethod
    async def subscribe_quote(self, stock_list: list[str]) -> AsyncIterator[dict]:
        """订阅实时行情推送.

        Args:
            stock_list: 股票代码列表

        Yields:
            实时行情数据
        """

    async def get_instrument_detail(self, stock_code: str) -> dict[str, Any] | None:
        """获取合约基础信息.

        Args:
            stock_code: 合约代码

        Returns:
            合约信息字典，找不到时返回 None
        """
        raise NotImplementedError("get_instrument_detail not implemented")

    async def get_instrument_type(self, stock_code: str) -> dict[str, bool] | None:
        """获取合约类型.

        Args:
            stock_code: 合约代码

        Returns:
            合约类型字典，如 {"stock": True, "fund": False}
        """
        raise NotImplementedError("get_instrument_type not implemented")

    async def get_full_tick(self, code_list: list[str]) -> dict[str, Any]:
        """获取全推数据（最新分笔快照）.

        Args:
            code_list: 代码列表，支持市场代码或合约代码

        Returns:
            全推数据字典 {stock_code: tick_data}
        """
        raise NotImplementedError("get_full_tick not implemented")

    async def get_divid_factors(
        self, stock_code: str, start_time: str = "", end_time: str = ""
    ) -> dict[str, Any]:
        """获取除权数据.

        Args:
            stock_code: 合约代码
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            除权数据
        """
        raise NotImplementedError("get_divid_factors not implemented")

    async def download_history_data(
        self,
        stock_code: str,
        period: str,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        """补充历史行情数据.

        Args:
            stock_code: 合约代码
            period: 周期
            start_time: 起始时间
            end_time: 结束时间
        """
        raise NotImplementedError("download_history_data not implemented")

    async def download_history_data2(
        self,
        stock_list: list[str],
        period: str,
        start_time: str = "",
        end_time: str = "",
    ) -> None:
        """批量补充历史行情数据.

        Args:
            stock_list: 合约代码列表
            period: 周期
            start_time: 起始时间
            end_time: 结束时间
        """
        raise NotImplementedError("download_history_data2 not implemented")

    async def get_financial_data(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
        start_time: str = "",
        end_time: str = "",
        report_type: str = "report_time",
    ) -> dict[str, Any]:
        """获取财务数据.

        Args:
            stock_list: 合约代码列表
            table_list: 财务数据表名称列表
            start_time: 起始时间
            end_time: 结束时间
            report_type: 报表筛选方式 "report_time" 或 "announce_time"

        Returns:
            财务数据字典
        """
        raise NotImplementedError("get_financial_data not implemented")

    async def download_financial_data(
        self,
        stock_list: list[str],
        table_list: list[str] | None = None,
    ) -> None:
        """下载财务数据.

        Args:
            stock_list: 合约代码列表
            table_list: 财务数据表名称列表
        """
        raise NotImplementedError("download_financial_data not implemented")

    async def get_trading_dates(
        self,
        market: str,
        start_time: str = "",
        end_time: str = "",
        count: int = -1,
    ) -> list[str]:
        """获取交易日列表.

        Args:
            market: 市场代码
            start_time: 起始时间
            end_time: 结束时间
            count: 数据个数

        Returns:
            交易日列表
        """
        raise NotImplementedError("get_trading_dates not implemented")

    async def get_trading_calendar(
        self,
        market: str,
        start_time: str = "",
        end_time: str = "",
    ) -> list[str]:
        """获取交易日历.

        Args:
            market: 市场代码
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            交易日列表
        """
        raise NotImplementedError("get_trading_calendar not implemented")

    async def get_sector_list(self) -> list[str]:
        """获取板块列表.

        Returns:
            板块名称列表
        """
        raise NotImplementedError("get_sector_list not implemented")

    async def download_sector_data(self) -> None:
        """下载板块分类信息."""
        raise NotImplementedError("download_sector_data not implemented")

    async def get_index_weight(self, index_code: str) -> dict[str, Any]:
        """获取指数成分权重信息.

        Args:
            index_code: 指数代码

        Returns:
            成分权重字典 {stock_code: weight}
        """
        raise NotImplementedError("get_index_weight not implemented")

    async def download_index_weight(self) -> None:
        """下载指数成分权重信息."""
        raise NotImplementedError("download_index_weight not implemented")

    async def get_holidays(self) -> list[str]:
        """获取节假日数据.

        Returns:
            节假日日期列表（8位字符串）
        """
        raise NotImplementedError("get_holidays not implemented")

    async def download_holiday_data(self) -> None:
        """下载节假日数据."""
        raise NotImplementedError("download_holiday_data not implemented")

    async def get_full_kline(
        self,
        stock_list: list[str],
        period: str = "1m",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """获取最新交易日K线全推数据.

        Args:
            stock_list: 合约代码列表
            period: 周期
            fields: 字段列表

        Returns:
            K线数据字典
        """
        raise NotImplementedError("get_full_kline not implemented")

    async def subscribe_whole_quote(
        self, code_list: list[str]
    ) -> AsyncIterator[dict]:
        """订阅全推行情数据.

        Args:
            code_list: 代码列表，支持市场代码或合约代码

        Yields:
            全推行情数据
        """
        raise NotImplementedError("subscribe_whole_quote not implemented")

    async def get_local_data(
        self,
        stock_list: list[str],
        fields: list[str],
        period: str = "1d",
        start_time: str = "",
        end_time: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """从本地数据文件获取行情数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表
            period: 周期
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            行情数据字典
        """
        raise NotImplementedError("get_local_data not implemented")
