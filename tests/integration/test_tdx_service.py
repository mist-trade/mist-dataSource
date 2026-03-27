"""Integration tests for TDX service."""

import pytest

from instance1.services.tdx_service import tdx_service


@pytest.mark.asyncio
async def test_get_sector_overview():
    """Test getting sector overview."""
    overview = await tdx_service.get_sector_overview("通达信88")

    assert "sector" in overview
    assert overview["sector"] == "通达信88"
    assert "total_stocks" in overview
    assert overview["total_stocks"] > 0
    assert "sample_data" in overview
