"""TDX (TongDaXin) adapter implementation using tqcenter SDK.

Note: This module requires tqcenter SDK which is only available on Windows.
The通达信终端 must be running and logged in before using this adapter.

对应 TDX SDK: tqcenter.tq (通达信官方提供的 tqcenter.py)

部署方式: 将通达信提供的 SDK 文件夹路径设置为 TDX_SDK_PATH 环境变量,
例如: TDX_SDK_PATH=D:/tdx/PYPlugins/user
SDK 目录结构 (通达信官方原始结构):
    D:/tdx/PYPlugins/
        TPythClient.dll
        user/
            tqcenter.py       ← 单文件模块, 包含 tq 类
代码会自动将 TDX_SDK_PATH 加入 sys.path, 使 from tqcenter import tq 可用.
TPythClient.dll 由 SDK 内部通过 Path(__file__).parents[1] 自动定位.
"""

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

from src.adapter.base import MarketDataAdapter
from src.core.config import settings
from src.core.exceptions import AdapterError


def _load_tq_module(sdk_path: str) -> Any:
    """从 SDK 路径加载 tq 模块.

    通达信官方 SDK 的 tqcenter 是一个单文件 tqcenter.py,
    不是标准 Python 包 (没有 __init__.py 的目录).

    按优先级尝试三种方式加载:
    1. 将 sdk_path 加入 sys.path 后 from tqcenter import tq
    2. 用 importlib 直接从文件路径加载 tqcenter.py

    Args:
        sdk_path: 包含 tqcenter.py 的目录路径

    Returns:
        tq 类

    Raises:
        ImportError: 无法找到或加载 tq 模块
    """
    sdk_dir = str(Path(sdk_path).resolve())

    # 方式 1: 加入 sys.path 后标准 import
    if sdk_dir not in sys.path:
        sys.path.insert(0, sdk_dir)
    try:
        from tqcenter import tq

        return tq
    except ImportError:
        pass

    # 方式 2: importlib 直接从文件路径加载
    tqcenter_py = os.path.join(sdk_dir, "tqcenter.py")
    if os.path.isfile(tqcenter_py):
        spec = importlib.util.spec_from_file_location("tqcenter", tqcenter_py)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["tqcenter"] = module
            spec.loader.exec_module(module)
            return module.tq

    raise ImportError(
        f"Cannot load tq module from SDK path: {sdk_path}. "
        f"Expected file: {sdk_dir}/tqcenter.py"
    )


class TDXAdapter(MarketDataAdapter):
    """通达信适配器 - 基于 tqcenter SDK.

    前置条件：通达信终端已启动并登录.

    Raises:
        ImportError: If tqcenter SDK is not available (non-Windows platforms)
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
            sdk_path = settings.tdx.sdk_path
            if not sdk_path:
                raise ImportError(
                    "TDX_SDK_PATH is not set. "
                    "Please set it to the directory containing tqcenter.py "
                    "(e.g. TDX_SDK_PATH=D:/tdx/PYPlugins/user)."
                )

            self._tq = _load_tq_module(sdk_path)
            # initialize 用 SDK 目录下的脚本路径作为策略标识
            # TDX 终端用此路径做策略名, 传 SDK 目录内的路径避免 "已有同名策略运行" 错误
            init_path = os.path.join(sdk_path, "mist_datasource.py")
            self._tq.initialize(init_path)
        except ImportError as e:
            raise ImportError(
                "tqcenter SDK is not available. "
                "Please set TDX_SDK_PATH to the directory containing tqcenter.py "
                "(e.g. TDX_SDK_PATH=D:/tdx/PYPlugins/user). "
                "Use TDXMockAdapter for development on other platforms."
            ) from e
        except Exception as e:
            raise AdapterError(f"Failed to initialize TDX adapter: {e}") from e

    async def shutdown(self) -> None:
        """Shutdown TDX connection."""
        self._tq = None

    async def get_stock_list(self, market: str = "0") -> list[str]:
        """获取市场股票列表.

        对应 TDX SDK: tq.get_stock_list(market)
        """
        try:
            return self._tq.get_stock_list(market)
        except Exception as e:
            raise AdapterError(f"Failed to get stock list: {e}") from e

    async def get_stock_list_in_sector(self, block_code: str = "通达信88", block_type: int = 0, list_type: int = 0) -> list[str]:
        """获取板块股票列表.

        对应 TDX SDK: tq.get_stock_list_in_sector(block_code, block_type, list_type)
        """
        try:
            return self._tq.get_stock_list_in_sector(block_code, block_type, list_type)
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

    # ---- Market Data Methods ----

    async def get_market_snapshot(self, stock_code: str, field_list: list[str] = []) -> dict:
        """获取实时行情快照.

        对应 TDX SDK: tq.get_market_snapshot(stock_code, field_list)

        Args:
            stock_code: 证券代码
            field_list: 字段筛选列表，传空则返回全部

        Returns:
            市场快照数据字典
        """
        try:
            return self._tq.get_market_snapshot(stock_code, field_list)
        except Exception as e:
            raise AdapterError(f"Failed to get market snapshot: {e}") from e

    async def get_divid_factors(self, stock_code: str, start_time: str = "", end_time: str = "") -> Any:
        """获取除权除息数据.

        对应 TDX SDK: tq.get_divid_factors(stock_code, start_time, end_time)

        Args:
            stock_code: 证券代码
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            除权除息数据 (DataFrame)
        """
        try:
            return self._tq.get_divid_factors(stock_code, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get dividend factors: {e}") from e

    async def get_gb_info(self, stock_code: str, date_list: list[str] = [], count: int = 1) -> list[dict]:
        """获取股本数据.

        对应 TDX SDK: tq.get_gb_info(stock_code, date_list, count)

        Args:
            stock_code: 证券代码
            date_list: 日期数组
            count: 日期有效个数

        Returns:
            股本数据列表
        """
        try:
            return self._tq.get_gb_info(stock_code, date_list, count)
        except Exception as e:
            raise AdapterError(f"Failed to get gb info: {e}") from e

    async def get_trading_dates(self, market: str = "SH", start_time: str = "", end_time: str = "", count: int = -1) -> list[str]:
        """获取交易日列表.

        对应 TDX SDK: tq.get_trading_dates(market, start_time, end_time, count)

        Args:
            market: 市场代码（暂固定为SH）
            start_time: 起始时间
            end_time: 结束时间
            count: 返回最近的count个交易日

        Returns:
            交易日列表
        """
        try:
            return self._tq.get_trading_dates(market, start_time, end_time, count)
        except Exception as e:
            raise AdapterError(f"Failed to get trading dates: {e}") from e

    async def refresh_cache(self, market: str = "AG", force: bool = False) -> dict:
        """刷新行情缓存.

        对应 TDX SDK: tq.refresh_cache(market, force)

        Args:
            market: 指定刷新的市场 ('AG'=A股, 'HK'=港股, 'US'=美股, 'QH'=期货等)
            force: 是否强制刷新

        Returns:
            刷新结果字典
        """
        try:
            return self._tq.refresh_cache(market, force)
        except Exception as e:
            raise AdapterError(f"Failed to refresh cache: {e}") from e

    async def refresh_kline(self, stock_list: list[str] = [], period: str = "1d") -> dict:
        """刷新K线缓存.

        对应 TDX SDK: tq.refresh_kline(stock_list, period)

        Args:
            stock_list: 证券代码列表
            period: 周期 (1d=日线, 1m=1分钟, 5m=5分钟)

        Returns:
            刷新结果字典
        """
        try:
            return self._tq.refresh_kline(stock_list, period)
        except Exception as e:
            raise AdapterError(f"Failed to refresh kline: {e}") from e

    async def download_file(self, stock_code: str = "", down_time: str = "", down_type: int = 1) -> dict:
        """下载特定数据文件.

        对应 TDX SDK: tq.download_file(stock_code, down_time, down_type)

        Args:
            stock_code: 证券代码
            down_time: 指定日期
            down_type: 下载类型 (1=10大股东, 2=ETF申赎, 3=最近舆情, 4=综合信息)

        Returns:
            下载结果字典
        """
        try:
            return self._tq.download_file(stock_code, down_time, down_type)
        except Exception as e:
            raise AdapterError(f"Failed to download file: {e}") from e

    # ---- Stock Info Methods ----

    async def get_stock_info(self, stock_code: str = "") -> dict:
        """获取股票基本信息.

        对应 TDX SDK: tq.get_stock_info(stock_code)

        Args:
            stock_code: 证券代码

        Returns:
            股票基本信息字典
        """
        try:
            return self._tq.get_stock_info(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get stock info: {e}") from e

    async def get_report_data(self, stock_code: str = "") -> dict:
        """获取报告数据.

        对应 TDX SDK: tq.get_report_data(stock_code)

        Args:
            stock_code: 证券代码

        Returns:
            报告数据字典
        """
        try:
            return self._tq.get_report_data(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get report data: {e}") from e

    async def get_more_info(self, stock_code: str = "", field_list: list[str] = []) -> dict:
        """获取更多信息.

        对应 TDX SDK: tq.get_more_info(stock_code, field_list)

        Args:
            stock_code: 证券代码
            field_list: 字段筛选列表，传空则返回全部

        Returns:
            更多信息字典
        """
        try:
            return self._tq.get_more_info(stock_code, field_list)
        except Exception as e:
            raise AdapterError(f"Failed to get more info: {e}") from e

    async def get_relation(self, stock_code: str = "") -> dict:
        """获取股票所属板块.

        对应 TDX SDK: tq.get_relation(stock_code)

        Args:
            stock_code: 证券代码

        Returns:
            板块关联信息字典
        """
        try:
            return self._tq.get_relation(stock_code)
        except Exception as e:
            raise AdapterError(f"Failed to get relation: {e}") from e

    # ---- Financial and Value Methods ----

    async def get_financial_data(
        self,
        stock_list: list[str],
        field_list: list[str],
        start_time: str = "",
        end_time: str = "",
        report_type: str = "announce_time",
    ) -> dict:
        """获取专业财务数据.

        对应 TDX SDK: tq.get_financial_data(
            stock_list, field_list, start_time, end_time, report_type
        )

        Args:
            stock_list: 证券代码列表
            field_list: 字段列表
            start_time: 起始时间
            end_time: 结束时间
            report_type: 报表筛选方式 ("announce_time" 或 "report_time")

        Returns:
            专业财务数据字典
        """
        try:
            return self._tq.get_financial_data(stock_list, field_list, start_time, end_time, report_type)
        except Exception as e:
            raise AdapterError(f"Failed to get financial data: {e}") from e

    async def get_financial_data_by_date(
        self, stock_list: list[str], field_list: list[str], year: int = 0, mmdd: int = 0
    ) -> dict:
        """获取指定日期专业财务数据.

        对应 TDX SDK: tq.get_financial_data_by_date(
            stock_list, field_list, year, mmdd
        )

        Args:
            stock_list: 证券代码列表
            field_list: 字段列表
            year: 年份 (0表示最新)
            mmdd: 月日 (0表示最新, 1表示倒数第2个, 以此类推)

        Returns:
            专业财务数据字典
        """
        try:
            return self._tq.get_financial_data_by_date(stock_list, field_list, year, mmdd)
        except Exception as e:
            raise AdapterError(f"Failed to get financial data by date: {e}") from e

    async def get_gp_one_data(self, stock_list: list[str], field_list: list[str]) -> dict:
        """获取股票单个数据.

        对应 TDX SDK: tq.get_gp_one_data(stock_list, field_list)

        Args:
            stock_list: 证券代码列表
            field_list: 字段列表

        Returns:
            股票单个数据字典
        """
        try:
            return self._tq.get_gp_one_data(stock_list, field_list)
        except Exception as e:
            raise AdapterError(f"Failed to get gp one data: {e}") from e

    async def get_bkjy_value(
        self, stock_list: list[str], field_list: list[str], start_time: str = "", end_time: str = ""
    ) -> dict:
        """获取板块交易数据.

        对应 TDX SDK: tq.get_bkjy_value(
            stock_list, field_list, start_time, end_time
        )

        Args:
            stock_list: 板块代码列表
            field_list: 字段列表
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            板块交易数据字典
        """
        try:
            return self._tq.get_bkjy_value(stock_list, field_list, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get bkjy value: {e}") from e

    async def get_bkjy_value_by_date(
        self, stock_list: list[str], field_list: list[str], year: int = 0, mmdd: int = 0
    ) -> dict:
        """获取指定日期板块交易数据.

        对应 TDX SDK: tq.get_bkjy_value_by_date(
            stock_list, field_list, year, mmdd
        )

        Args:
            stock_list: 板块代码列表
            field_list: 字段列表
            year: 年份 (0表示最新)
            mmdd: 月日 (0表示最新, 1表示倒数第2个, 以此类推)

        Returns:
            板块交易数据字典
        """
        try:
            return self._tq.get_bkjy_value_by_date(stock_list, field_list, year, mmdd)
        except Exception as e:
            raise AdapterError(f"Failed to get bkjy value by date: {e}") from e

    async def get_gpjy_value(
        self, stock_list: list[str], field_list: list[str], start_time: str = "", end_time: str = ""
    ) -> dict:
        """获取股票交易数据.

        对应 TDX SDK: tq.get_gpjy_value(
            stock_list, field_list, start_time, end_time
        )

        Args:
            stock_list: 证券代码列表
            field_list: 字段列表
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            股票交易数据字典
        """
        try:
            return self._tq.get_gpjy_value(stock_list, field_list, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get gpjy value: {e}") from e

    async def get_gpjy_value_by_date(
        self, stock_list: list[str], field_list: list[str], year: int = 0, mmdd: int = 0
    ) -> dict:
        """获取指定日期股票交易数据.

        对应 TDX SDK: tq.get_gpjy_value_by_date(
            stock_list, field_list, year, mmdd
        )

        Args:
            stock_list: 证券代码列表
            field_list: 字段列表
            year: 年份 (0表示最新)
            mmdd: 月日 (0表示最新, 1表示倒数第2个, 以此类推)

        Returns:
            股票交易数据字典
        """
        try:
            return self._tq.get_gpjy_value_by_date(stock_list, field_list, year, mmdd)
        except Exception as e:
            raise AdapterError(f"Failed to get gpjy value by date: {e}") from e

    async def get_scjy_value(self, field_list: list[str], start_time: str = "", end_time: str = "") -> dict:
        """获取市场交易数据.

        对应 TDX SDK: tq.get_scjy_value(field_list, start_time, end_time)

        Args:
            field_list: 字段列表
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            市场交易数据字典
        """
        try:
            return self._tq.get_scjy_value(field_list, start_time, end_time)
        except Exception as e:
            raise AdapterError(f"Failed to get scjy value: {e}") from e

    async def get_scjy_value_by_date(self, field_list: list[str], year: int = 0, mmdd: int = 0) -> dict:
        """获取指定日期市场交易数据.

        对应 TDX SDK: tq.get_scjy_value_by_date(field_list, year, mmdd)

        Args:
            field_list: 字段列表
            year: 年份 (0表示最新)
            mmdd: 月日 (0表示最新, 1表示倒数第2个, 以此类推)

        Returns:
            市场交易数据字典
        """
        try:
            return self._tq.get_scjy_value_by_date(field_list, year, mmdd)
        except Exception as e:
            raise AdapterError(f"Failed to get scjy value by date: {e}") from e
