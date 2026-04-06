"""Integration tests for TDX service."""

import pytest

import tdx.main
from src.adapter import create_tdx_adapter
from tdx.services.tdx_service import TDXService


@pytest.mark.asyncio
async def test_get_sector_overview():
    """Test getting sector overview."""
    adapter = create_tdx_adapter()
    await adapter.initialize()

    service = TDXService()
    # Patch the adapter reference in the main module
    original_adapter = tdx.main.tdx_adapter
    tdx.main.tdx_adapter = adapter

    try:
        # The service internally calls get_stock_list_in_sector
        overview = await service.get_sector_overview("通达信88")

        assert "sector" in overview
        assert overview["sector"] == "通达信88"
        assert "total_stocks" in overview
        assert overview["total_stocks"] > 0
        assert "sample_data" in overview
    finally:
        tdx.main.tdx_adapter = original_adapter
        await adapter.shutdown()
