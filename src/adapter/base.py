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
    async def get_stock_list(self, market: str = "0") -> list[str]:
        """获取市场股票列表.

        Args:
            market: 市场代码，默认 "0" (A股)

        Returns:
            股票代码列表
        """

    @abstractmethod
    async def get_stock_list_in_sector(self, block_code: str, block_type: int = 0, list_type: int = 0) -> list[str]:
        """获取板块股票列表.

        Args:
            block_code: 板块代码，如 "通达信88"
            block_type: 板块类型，默认 0
            list_type: 列表类型，默认 0

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
        report_type: str = "announce_time",
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

    async def get_sector_list(self, list_type: int = 0) -> list[str]:
        """获取板块列表.

        Args:
            list_type: 列表类型，默认 0

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

    # ---- Market Data Methods ----

    async def get_market_snapshot(self, stock_code: str) -> dict[str, Any]:
        """获取市场快照数据.

        Args:
            stock_code: 合约代码

        Returns:
            市场快照数据
        """
        raise NotImplementedError("get_market_snapshot not implemented")

    async def get_gb_info(self, stock_code: str) -> dict[str, Any]:
        """获取股本信息.

        Args:
            stock_code: 合约代码

        Returns:
            股本信息
        """
        raise NotImplementedError("get_gb_info not implemented")

    async def refresh_cache(self, stock_code: str) -> None:
        """刷新缓存数据.

        Args:
            stock_code: 合约代码
        """
        raise NotImplementedError("refresh_cache not implemented")

    async def refresh_kline(self, stock_code: str) -> None:
        """刷新K线数据.

        Args:
            stock_code: 合约代码
        """
        raise NotImplementedError("refresh_kline not implemented")

    async def download_file(self, file_type: str, stock_code: str = "") -> None:
        """下载文件数据.

        Args:
            file_type: 文件类型
            stock_code: 合约代码
        """
        raise NotImplementedError("download_file not implemented")

    # ---- Stock Info Methods ----

    async def get_stock_info(self, stock_code: str) -> dict[str, Any]:
        """获取股票信息.

        Args:
            stock_code: 合约代码

        Returns:
            股票信息
        """
        raise NotImplementedError("get_stock_info not implemented")

    async def get_report_data(self, stock_code: str) -> dict[str, Any]:
        """获取报告数据.

        Args:
            stock_code: 合约代码

        Returns:
            报告数据
        """
        raise NotImplementedError("get_report_data not implemented")

    async def get_more_info(self, stock_code: str) -> dict[str, Any]:
        """获取更多信息.

        Args:
            stock_code: 合约代码

        Returns:
            更多信息
        """
        raise NotImplementedError("get_more_info not implemented")

    async def get_relation(self, stock_code: str) -> dict[str, Any]:
        """获取关联信息.

        Args:
            stock_code: 合约代码

        Returns:
            关联信息
        """
        raise NotImplementedError("get_relation not implemented")

    # ---- Financial Methods ----

    async def get_financial_data_by_date(
        self,
        stock_list: list[str],
        table_list: list[str],
        date: str,
        report_type: str = "announce_time",
    ) -> dict[str, Any]:
        """获取指定日期财务数据.

        Args:
            stock_list: 合约代码列表
            table_list: 财务数据表名称列表
            date: 日期
            report_type: 报表筛选方式

        Returns:
            财务数据字典
        """
        raise NotImplementedError("get_financial_data_by_date not implemented")

    async def get_gp_one_data(
        self, stock_list: list[str], fields: list[str]
    ) -> dict[str, Any]:
        """获取股票一级数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表

        Returns:
            数据字典
        """
        raise NotImplementedError("get_gp_one_data not implemented")

    # ---- Value Methods ----

    async def get_bkjy_value(
        self, stock_list: list[str], fields: list[str]
    ) -> dict[str, Any]:
        """获取板块交易数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表

        Returns:
            板块交易数据
        """
        raise NotImplementedError("get_bkjy_value not implemented")

    async def get_bkjy_value_by_date(
        self, stock_list: list[str], fields: list[str], date: str
    ) -> dict[str, Any]:
        """获取指定日期板块交易数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表
            date: 日期

        Returns:
            板块交易数据
        """
        raise NotImplementedError("get_bkjy_value_by_date not implemented")

    async def get_gpjy_value(
        self, stock_list: list[str], fields: list[str]
    ) -> dict[str, Any]:
        """获取股票交易数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表

        Returns:
            股票交易数据
        """
        raise NotImplementedError("get_gpjy_value not implemented")

    async def get_gpjy_value_by_date(
        self, stock_list: list[str], fields: list[str], date: str
    ) -> dict[str, Any]:
        """获取指定日期股票交易数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表
            date: 日期

        Returns:
            股票交易数据
        """
        raise NotImplementedError("get_gpjy_value_by_date not implemented")

    async def get_scjy_value(
        self, stock_list: list[str], fields: list[str]
    ) -> dict[str, Any]:
        """获取市场交易数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表

        Returns:
            市场交易数据
        """
        raise NotImplementedError("get_scjy_value not implemented")

    async def get_scjy_value_by_date(
        self, stock_list: list[str], fields: list[str], date: str
    ) -> dict[str, Any]:
        """获取指定日期市场交易数据.

        Args:
            stock_list: 合约代码列表
            fields: 字段列表
            date: 日期

        Returns:
            市场交易数据
        """
        raise NotImplementedError("get_scjy_value_by_date not implemented")

    # ---- Sector Methods ----

    async def get_user_sector(self, name: str = "") -> list[str]:
        """获取自定义板块.

        Args:
            name: 板块名称，留空返回所有板块

        Returns:
            股票代码列表
        """
        raise NotImplementedError("get_user_sector not implemented")

    async def create_sector(self, name: str, stocks: list[str]) -> None:
        """创建自定义板块.

        Args:
            name: 板块名称
            stocks: 股票代码列表
        """
        raise NotImplementedError("create_sector not implemented")

    async def delete_sector(self, name: str) -> None:
        """删除自定义板块.

        Args:
            name: 板块名称
        """
        raise NotImplementedError("delete_sector not implemented")

    async def rename_sector(self, old_name: str, new_name: str) -> None:
        """重命名自定义板块.

        Args:
            old_name: 原板块名称
            new_name: 新板块名称
        """
        raise NotImplementedError("rename_sector not implemented")

    async def clear_sector(self, name: str) -> None:
        """清空自定义板块.

        Args:
            name: 板块名称
        """
        raise NotImplementedError("clear_sector not implemented")

    async def send_user_block(self, block_code: str, stocks: list[str]) -> None:
        """发送自定义板块到通达信终端.

        Args:
            block_code: 板块代码
            stocks: 股票代码列表
        """
        raise NotImplementedError("send_user_block not implemented")

    # ---- ETF Methods ----

    async def get_kzz_info(self, stock_code: str = "", field_list: list[str] | None = None) -> dict[str, Any]:
        """获取可转债信息.

        Args:
            stock_code: 可转债代码
            field_list: 字段列表

        Returns:
            可转债信息
        """
        raise NotImplementedError("get_kzz_info not implemented")

    async def get_ipo_info(self, ipo_type: int = 0, ipo_date: int = 0) -> dict[str, Any]:
        """获取新股信息.

        Args:
            ipo_type: IPO类型
            ipo_date: IPO日期

        Returns:
            新股信息
        """
        raise NotImplementedError("get_ipo_info not implemented")

    async def get_trackzs_etf_info(self, zs_code: str = "") -> dict[str, Any]:
        """获取ETF跟踪指数信息.

        Args:
            zs_code: 指数代码

        Returns:
            ETF跟踪指数信息
        """
        raise NotImplementedError("get_trackzs_etf_info not implemented")

    # ---- Subscription Methods ----

    async def subscribe_hq(self, stock_list: list[str]) -> None:
        """订阅行情.

        Args:
            stock_list: 股票代码列表
        """
        raise NotImplementedError("subscribe_hq not implemented")

    async def unsubscribe_hq(self, stock_list: list[str]) -> None:
        """取消订阅行情.

        Args:
            stock_list: 股票代码列表
        """
        raise NotImplementedError("unsubscribe_hq not implemented")

    async def get_subscribe_list(self) -> list[str]:
        """获取订阅列表.

        Returns:
            订阅的股票代码列表
        """
        raise NotImplementedError("get_subscribe_list not implemented")

    # ---- Client Methods ----

    async def exec_to_tdx(self, cmd: str = "", param: str = "") -> dict[str, Any]:
        """调用客户端功能接口.

        Args:
            cmd: 命令
            param: 参数

        Returns:
            执行结果
        """
        raise NotImplementedError("exec_to_tdx not implemented")

    # ---- Trading Methods ----

    async def order_stock(
        self, stock_code: str, order_type: int, volume: int, price_type: int, price: float
    ) -> int:
        """下单.

        Args:
            stock_code: 合约代码
            order_type: 下单类型
            volume: 数量
            price_type: 价格类型
            price: 价格

        Returns:
            订单编号
        """
        raise NotImplementedError("order_stock not implemented")

    async def cancel_order_stock(self, order_id: int) -> int:
        """撤单.

        Args:
            order_id: 订单编号

        Returns:
            撤单结果
        """
        raise NotImplementedError("cancel_order_stock not implemented")

    async def query_stock_orders(self, order_id: int = 0) -> list[dict[str, Any]]:
        """查委托.

        Args:
            order_id: 订单编号

        Returns:
            委托列表
        """
        raise NotImplementedError("query_stock_orders not implemented")

    async def query_stock_positions(self) -> list[dict[str, Any]]:
        """查持仓.

        Returns:
            持仓列表
        """
        raise NotImplementedError("query_stock_positions not implemented")

    async def query_stock_asset(self) -> dict[str, Any]:
        """查资金.

        Returns:
            资金信息
        """
        raise NotImplementedError("query_stock_asset not implemented")

    async def stock_account(self) -> dict[str, Any]:
        """查询账户信息.

        Returns:
            账户信息
        """
        raise NotImplementedError("stock_account not implemented")

    # ---- Formula Methods ----

    async def formula_format_data(self, data: str) -> dict[str, Any]:
        """格式化公式数据.

        Args:
            data: 数据

        Returns:
            格式化数据
        """
        raise NotImplementedError("formula_format_data not implemented")

    async def formula_set_data(self, name: str, data: str) -> None:
        """设置公式数据.

        Args:
            name: 名称
            data: 数据
        """
        raise NotImplementedError("formula_set_data not implemented")

    async def formula_set_data_info(
        self, name: str, info: dict[str, Any]
    ) -> None:
        """设置公式数据信息.

        Args:
            name: 名称
            info: 信息
        """
        raise NotImplementedError("formula_set_data_info not implemented")

    async def formula_get_data(self, name: str) -> dict[str, Any]:
        """获取公式数据.

        Args:
            name: 名称

        Returns:
            数据
        """
        raise NotImplementedError("formula_get_data not implemented")

    async def formula_zb(
        self, formula: str, params: list[Any] | None = None
    ) -> dict[str, Any]:
        """执行公式指标.

        Args:
            formula: 公式
            params: 参数

        Returns:
            结果
        """
        raise NotImplementedError("formula_zb not implemented")

    async def formula_exp(self, formula: str) -> dict[str, Any]:
        """执行公式表达式.

        Args:
            formula: 公式

        Returns:
            结果
        """
        raise NotImplementedError("formula_exp not implemented")

    async def formula_xg(self, formula: str) -> list[str]:
        """执行公式选股.

        Args:
            formula: 公式

        Returns:
            股票代码列表
        """
        raise NotImplementedError("formula_xg not implemented")

    async def formula_process(
        self, formula: str, stock_code: str
    ) -> dict[str, Any]:
        """执行公式处理.

        Args:
            formula: 公式
            stock_code: 合约代码

        Returns:
            结果
        """
        raise NotImplementedError("formula_process not implemented")

    async def formula_process_mul_xg(
        self, formulas: list[str], stock_list: list[str]
    ) -> dict[str, list[str]]:
        """执行多公式选股.

        Args:
            formulas: 公式列表
            stock_list: 合约代码列表

        Returns:
            结果
        """
        raise NotImplementedError("formula_process_mul_xg not implemented")

    async def formula_process_mul_zb(
        self, formulas: list[str], stock_list: list[str]
    ) -> dict[str, Any]:
        """执行多公式指标.

        Args:
            formulas: 公式列表
            stock_list: 合约代码列表

        Returns:
            结果
        """
        raise NotImplementedError("formula_process_mul_zb not implemented")

    # ---- Client Communication Methods ----

    async def send_message(self, message: str) -> None:
        """发送消息.

        Args:
            message: 消息
        """
        raise NotImplementedError("send_message not implemented")

    async def send_file(self, file_path: str) -> None:
        """发送文件.

        Args:
            file_path: 文件路径
        """
        raise NotImplementedError("send_file not implemented")

    async def send_warn(self, message: str) -> None:
        """发送警告.

        Args:
            message: 消息
        """
        raise NotImplementedError("send_warn not implemented")

    async def send_bt_data(self, data: dict[str, Any]) -> None:
        """发送回测数据.

        Args:
            data: 数据
        """
        raise NotImplementedError("send_bt_data not implemented")

    async def print_to_tdx(self, message: str) -> None:
        """打印到通达信终端.

        Args:
            message: 消息
        """
        raise NotImplementedError("print_to_tdx not implemented")
