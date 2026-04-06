"""Live integration tests for TDX adapter (Windows only).

These tests require the TDX terminal to be running and are marked with @pytest.mark.live.
Run with: uv run pytest tests/integration/test_tdx_live.py -v -m live

Only run on Windows with TDX terminal installed and running.
"""

import pytest

from src.adapter import create_tdx_adapter


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_market_snapshot():
    """Test get_market_snapshot with real TDX SDK."""
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_market_snapshot("600519.SH")
        assert isinstance(result, dict)
        assert "Now" in result or "ErrorId" in result
        print(f"Market snapshot: {result.get('Now', 'N/A')}")
    finally:
        await adapter.shutdown()


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_stock_list_in_sector():
    """Test get_stock_list_in_sector with real TDX SDK."""
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_stock_list_in_sector("通达信88")
        assert isinstance(result, list)
        assert len(result) > 0
        print(f"Stock count in sector: {len(result)}")
    finally:
        await adapter.shutdown()


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_stock_list():
    """Test get_stock_list (market-based) with real TDX SDK."""
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_stock_list("0")
        assert isinstance(result, list)
        assert len(result) > 0
        print(f"Stock count in market: {len(result)}")
    finally:
        await adapter.shutdown()


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_financial_data():
    """Test get_financial_data with real TDX SDK."""
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_financial_data(
            ["600519.SH"],
            ["FN193", "FN194"],
            "",
            "",
            "announce_time"
        )
        assert isinstance(result, dict)
        assert "600519.SH" in result or len(result) > 0
        print(f"Financial data keys: {list(result.keys())}")
    finally:
        await adapter.shutdown()


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_sector_list():
    """Test get_sector_list with real TDX SDK."""
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_sector_list(0)
        assert isinstance(result, list)
        print(f"Sector count: {len(result)}")
    finally:
        await adapter.shutdown()


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_get_kzz_info():
    """Test get_kzz_info with real TDX SDK."""
    adapter = create_tdx_adapter()
    await adapter.initialize()
    try:
        result = await adapter.get_kzz_info("", [])
        assert isinstance(result, dict)
        print(f"Convertible bond info: {list(result.keys())[:5]}...")  # Show first 5 keys
    finally:
        await adapter.shutdown()
