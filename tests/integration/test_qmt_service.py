"""Integration tests for QMT service."""

import pytest

import qmt.main
from qmt.services.qmt_service import QMTService
from src.adapter import create_qmt_adapter


@pytest.mark.asyncio
async def test_get_sector_overview():
    """Test getting sector overview."""
    adapter = create_qmt_adapter(path="/test", account_id="12345")
    await adapter.initialize()

    service = QMTService()
    original_adapter = qmt.main.qmt_adapter
    qmt.main.qmt_adapter = adapter

    try:
        overview = await service.get_sector_overview()

        assert "sector" in overview
        assert "total_stocks" in overview
        assert "sample_data" in overview
    finally:
        qmt.main.qmt_adapter = original_adapter
        await adapter.shutdown()
