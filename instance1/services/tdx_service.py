"""TDX service layer for business logic orchestration.

This module contains higher-level business logic that uses the TDX adapter.
For complex operations that involve multiple adapter calls, implement them here.
"""

from typing import Any

from instance1.main import tdx_adapter
from src.core.exceptions import AdapterError


class TDXService:
    """TDX 业务服务类."""

    async def get_sector_overview(self, sector: str = "通达信88") -> dict[str, Any]:
        """获取板块概览信息.

        Args:
            sector: 板块名称

        Returns:
            包含股票列表和最新行情的概览信息
        """
        if not tdx_adapter:
            raise AdapterError("TDX adapter not initialized")

        # 获取股票列表
        stocks = await tdx_adapter.get_stock_list(sector)

        # 获取最新行情（简化版，只获取收盘价）
        try:
            market_data = await tdx_adapter.get_market_data(
                stock_list=stocks[:10],  # 限制数量避免请求过大
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


# Singleton instance
tdx_service = TDXService()
