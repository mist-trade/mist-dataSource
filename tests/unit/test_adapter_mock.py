"""Unit tests for mock adapters."""

import pytest

from src.adapter import create_qmt_adapter, create_tdx_adapter


@pytest.mark.asyncio
async def test_tdx_mock_adapter():
    """Test TDX mock adapter functionality."""
    adapter = create_tdx_adapter()
    await adapter.initialize()

    # Test get_stock_list_in_sector
    stocks = await adapter.get_stock_list_in_sector()
    assert isinstance(stocks, list)
    assert len(stocks) > 0

    # Test get_market_data
    data = await adapter.get_market_data(
        stock_list=["SH600519"],
        fields=["Close", "Volume"],
        period="1d",
    )
    assert "Close" in data
    assert "Volume" in data

    await adapter.shutdown()


@pytest.mark.asyncio
async def test_qmt_mock_adapter():
    """Test QMT mock adapter functionality."""
    adapter = create_qmt_adapter(path="/mock/path", account_id="12345")
    await adapter.initialize()

    # Test get_stock_list_in_sector
    stocks = await adapter.get_stock_list_in_sector()
    assert isinstance(stocks, list)
    assert len(stocks) > 0

    # Test get_market_data
    data = await adapter.get_market_data(
        stock_list=["SH600519"],
        fields=["Close"],
        period="1d",
    )
    assert "Close" in data

    # Test trading methods (mock)
    order_id = await adapter.order_stock("SH600519", 0, 100, 0, 1800.0)
    assert isinstance(order_id, int)

    positions = await adapter.query_positions()
    assert isinstance(positions, list)

    await adapter.shutdown()
