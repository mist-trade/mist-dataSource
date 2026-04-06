"""TDX 业务服务层.

封装 TDX 适配器的高层业务逻辑，组合多个底层适配器调用实现复杂操作。
对应 TDX SDK: tqcenter.tq
"""

from typing import Any

import tdx.main
from src.core.exceptions import AdapterError


class TDXService:
    """TDX 业务服务类.

    提供板块概览等组合业务操作，内部通过 MarketDataAdapter 调用 TDX SDK.
    对应 TDX SDK: tqcenter.tq

    Attributes:
        无实例属性，依赖模块级 tdx_adapter 单例.
    """

    async def get_sector_overview(self, sector: str = "通达信88") -> dict[str, Any]:
        """获取板块概览信息.

        组合调用 get_stock_list + get_market_data，返回板块股票列表及前10只股票的最新行情快照.

        对应 TDX SDK:
            - tq.get_stock_list_in_sector(sector)
            - tq.get_market_data(stock_list, field_list, period, ...)

        Args:
            sector: 板块名称，默认 "通达信88"

        Returns:
            包含以下字段的字典:
            - sector (str): 板块名称
            - total_stocks (int): 板块内股票总数
            - sample_data (dict[str, Any]): 前10只股票的最新日线行情（Close, Volume）

        Raises:
            AdapterError: TDX 适配器未初始化或行情数据获取失败

        Examples:
            >>> overview = await tdx_service.get_sector_overview("通达信88")
            >>> print(overview["total_stocks"])
            88
        """
        adapter = tdx.main.tdx_adapter
        if not adapter:
            raise AdapterError("TDX adapter not initialized")

        stocks = await adapter.get_stock_list_in_sector(sector)

        try:
            market_data = await adapter.get_market_data(
                stock_list=stocks[:10],
                fields=["Close", "Volume"],
                period="1d",
                start_time="",
                end_time="",
            )

            return {
                "sector": sector,
                "total_stocks": len(stocks),
                "sample_data": market_data,
            }
        except Exception as e:
            raise AdapterError(f"Failed to get sector overview: {e}") from e


tdx_service = TDXService()
