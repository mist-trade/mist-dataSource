"""QMT service layer for business logic orchestration.

This module contains higher-level business logic that uses the QMT adapter,
including both market data and trading operations.
"""

from typing import Any

from qmt.main import qmt_adapter
from src.core.exceptions import AdapterError


class QMTService:
    """QMT 业务服务类."""

    async def get_account_overview(self) -> dict[str, Any]:
        """获取账户概览信息.

        Returns:
            包含持仓和当日委托的账户概览
        """
        if not qmt_adapter:
            raise AdapterError("QMT adapter not initialized")

        try:
            positions = await qmt_adapter.query_positions()
            orders = await qmt_adapter.query_orders()

            return {
                "positions": positions,
                "position_count": len(positions),
                "orders": orders,
                "order_count": len(orders),
            }
        except Exception as e:
            raise AdapterError(f"Failed to get account overview: {e}") from e

    async def place_and_monitor_order(
        self,
        stock_code: str,
        order_type: int,
        volume: int,
        price_type: int,
        price: float = 0.0,
    ) -> dict[str, Any]:
        """下单并返回监控信息.

        Args:
            stock_code: 股票代码
            order_type: 订单类型（0=买，1=卖）
            volume: 委托数量
            price_type: 价格类型
            price: 委托价格

        Returns:
            订单信息和账户概览
        """
        if not qmt_adapter:
            raise AdapterError("QMT adapter not initialized")

        try:
            order_id = await qmt_adapter.order_stock(
                stock_code, order_type, volume, price_type, price
            )

            # 获取更新后的账户信息
            overview = await self.get_account_overview()

            return {
                "order_id": order_id,
                "stock_code": stock_code,
                "order_type": "buy" if order_type == 0 else "sell",
                "volume": volume,
                "price": price,
                "account_overview": overview,
            }
        except Exception as e:
            raise AdapterError(f"Failed to place order: {e}") from e


# Singleton instance
qmt_service = QMTService()
