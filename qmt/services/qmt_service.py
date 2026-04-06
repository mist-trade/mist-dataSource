"""QMT 业务服务层.

封装 QMT 适配器的高层业务逻辑，组合多个底层适配器调用实现复杂操作。
对应 QMT SDK: xtquant.xtdata
"""

from typing import Any

import qmt.main
from src.core.exceptions import AdapterError


class QMTService:
    """QMT 业务服务类.

    提供板块概览等组合业务操作，内部通过 MarketDataAdapter 调用 QMT SDK.
    对应 QMT SDK: xtquant.xtdata
    """

    async def get_sector_overview(self, sector: str = "沪深300") -> dict[str, Any]:
        """获取板块概览信息.

        组合调用 get_stock_list + get_market_data，返回板块股票列表及前10只股票的最新行情快照.

        对应 QMT SDK:
            - xtdata.get_stock_list_in_sector(sector)
            - xtdata.get_market_data(stock_list, field_list, period, ...)

        Args:
            sector: 板块名称，默认 "沪深300"

        Returns:
            包含以下字段的字典:
            - sector (str): 板块名称
            - total_stocks (int): 板块内股票总数
            - sample_data (dict[str, Any]): 前10只股票的最新日线行情（close, volume）
        """
        adapter = qmt.main.qmt_adapter
        if not adapter:
            raise AdapterError("QMT adapter not initialized")

        stocks = await adapter.get_stock_list_in_sector(sector)

        try:
            market_data = await adapter.get_market_data(
                stock_list=stocks[:10],
                fields=["close", "volume"],
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

    async def get_account_overview(self) -> dict[str, Any]:
        """获取账户概览信息.

        组合调用 query_positions + query_stock_orders，返回账户持仓和委托信息.

        Args:
            无

        Returns:
            包含以下字段的字典:
            - positions (list): 持仓列表
            - position_count (int): 持仓数量
            - orders (list): 委托列表
            - order_count (int): 委托数量
        """
        adapter = qmt.main.qmt_adapter
        if not adapter:
            raise AdapterError("QMT adapter not initialized")

        try:
            positions = await adapter.query_positions()
            orders = await adapter.query_stock_orders()

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
        price: float,
    ) -> dict[str, Any]:
        """下单并监控.

        组合调用 order_stock + get_account_overview，返回下单结果和账户概览.

        Args:
            stock_code: 合约代码
            order_type: 下单类型 (0=买入, 1=卖出)
            volume: 数量
            price_type: 价格类型
            price: 价格

        Returns:
            包含以下字段的字典:
            - order_id (int): 订单编号
            - stock_code (str): 合约代码
            - order_type (str): 下单类型描述
            - account_overview (dict): 账户概览
        """
        adapter = qmt.main.qmt_adapter
        if not adapter:
            raise AdapterError("QMT adapter not initialized")

        try:
            order_id = await adapter.order_stock(stock_code, order_type, volume, price_type, price)
            account_overview = await self.get_account_overview()

            order_type_str = "buy" if order_type == 0 else "sell"

            return {
                "order_id": order_id,
                "stock_code": stock_code,
                "order_type": order_type_str,
                "account_overview": account_overview,
            }
        except Exception as e:
            raise AdapterError(f"Failed to place and monitor order: {e}") from e


qmt_service = QMTService()
