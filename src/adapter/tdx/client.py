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
