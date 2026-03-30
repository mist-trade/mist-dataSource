"""Trading REST API routes for QMT adapter.

These routes are specific to QMT as TDX does not support trading.
"""

from fastapi import APIRouter, HTTPException

from qmt.main import qmt_adapter

router = APIRouter()


@router.post("/order")
async def place_order(
    stock_code: str,
    order_type: int,  # 0=买, 1=卖
    volume: int,
    price_type: int,  # 价格类型
    price: float = 0.0,
):
    """下单.

    Args:
        stock_code: 股票代码
        order_type: 订单类型（0=买，1=卖）
        volume: 委托数量
        price_type: 价格类型
        price: 委托价格

    Returns:
        订单 ID

    Raises:
        HTTPException: If adapter is not initialized or order fails
    """
    if not qmt_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        order_id = await qmt_adapter.order_stock(
            stock_code, order_type, volume, price_type, price
        )
        return {"order_id": order_id, "status": "submitted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/order/{order_id}")
async def cancel_order(order_id: int):
    """撤单.

    Args:
        order_id: 订单 ID

    Returns:
        操作结果

    Raises:
        HTTPException: If adapter is not initialized or cancellation fails
    """
    if not qmt_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        await qmt_adapter.cancel_order(order_id)
        return {"order_id": order_id, "status": "cancelled"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/positions")
async def get_positions():
    """查询持仓.

    Returns:
        持仓列表

    Raises:
        HTTPException: If adapter is not initialized or query fails
    """
    if not qmt_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        positions = await qmt_adapter.query_positions()
        return {"positions": positions, "count": len(positions)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/orders")
async def get_orders():
    """查询当日委托.

    Returns:
        委托列表

    Raises:
        HTTPException: If adapter is not initialized or query fails
    """
    if not qmt_adapter:
        raise HTTPException(status_code=503, detail="Adapter not initialized")

    try:
        orders = await qmt_adapter.query_orders()
        return {"orders": orders, "count": len(orders)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
