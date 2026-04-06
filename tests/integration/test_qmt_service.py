"""Integration tests for QMT service."""

import pytest

import qmt.main
from src.adapter import create_qmt_adapter
from qmt.services.qmt_service import QMTService


@pytest.mark.asyncio
async def test_get_account_overview():
    """Test getting account overview."""
    adapter = create_qmt_adapter(path="/test", account_id="12345")
    await adapter.initialize()

    service = QMTService()
    # Patch the adapter reference in the main module
    original_adapter = qmt.main.qmt_adapter
    qmt.main.qmt_adapter = adapter

    try:
        overview = await service.get_account_overview()

        assert "positions" in overview
        assert "position_count" in overview
        assert "orders" in overview
        assert "order_count" in overview
    finally:
        qmt.main.qmt_adapter = original_adapter
        await adapter.shutdown()


@pytest.mark.asyncio
async def test_place_and_monitor_order():
    """Test placing an order and getting account overview."""
    adapter = create_qmt_adapter(path="/test", account_id="12345")
    await adapter.initialize()

    service = QMTService()
    # Patch the adapter reference in the main module
    original_adapter = qmt.main.qmt_adapter
    qmt.main.qmt_adapter = adapter

    try:
        result = await service.place_and_monitor_order(
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
    finally:
        qmt.main.qmt_adapter = original_adapter
        await adapter.shutdown()
