"""Unit tests for mock adapters."""

import pytest

from src.adapter_legacy import create_tdx_legacy_adapter


@pytest.mark.asyncio
async def test_tdx_mock_adapter():
    """Test TDX mock adapter functionality."""
    adapter = create_tdx_legacy_adapter()
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
