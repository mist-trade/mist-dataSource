"""Integration tests for TDX service."""

import pytest

from tdx.services.tdx_service import TDXService
from src.adapter import create_tdx_adapter


@pytest.mark.asyncio
async def test_get_sector_overview():
    """Test getting sector overview."""
    adapter = create_tdx_adapter()
    await adapter.initialize()

    service = TDXService()
    # Patch the adapter reference
    import tdx.services.tdx_service as tdx_service_module
    original_adapter = tdx_service_module.tdx_adapter
    tdx_service_module.tdx_adapter = adapter

    try:
        overview = await service.get_sector_overview("通达信88")

        assert "sector" in overview
        assert overview["sector"] == "通达信88"
        assert "total_stocks" in overview
        assert overview["total_stocks"] > 0
        assert "sample_data" in overview
    finally:
        tdx_service_module.tdx_adapter = original_adapter
        await adapter.shutdown()
