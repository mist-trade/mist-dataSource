"""Integration tests for QMT service."""

import pytest

from instance2.services.qmt_service import qmt_service


@pytest.mark.asyncio
async def test_get_account_overview():
    """Test getting account overview."""
    overview = await qmt_service.get_account_overview()

    assert "positions" in overview
    assert "position_count" in overview
    assert "orders" in overview
    assert "order_count" in overview


@pytest.mark.asyncio
async def test_place_and_monitor_order():
    """Test placing an order and getting account overview."""
    result = await qmt_service.place_and_monitor_order(
        stock_code="SH600519",
        order_type=0,  # buy
        volume=100,
        price_type=0,
        price=1800.0,
    )

    assert "order_id" in result
    assert result["stock_code"] == "SH600519"
    assert result["order_type"] == "buy"
    assert "account_overview" in result
