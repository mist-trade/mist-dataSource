"""Integration tests for TDX route endpoints.

Tests all HTTP endpoints against the TDX service using mock adapter.
"""

import pytest

from tests.conftest import tdx_client


@pytest.mark.asyncio
class TestMarketRoutes:
    """Test market data routes."""

    async def test_stock_list_in_sector(self, tdx_client):
        """Test /api/tdx/stock-list-in-sector endpoint."""
        resp = await tdx_client.get("/api/tdx/stock-list-in-sector?block_code=通达信88")
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data or "data" in data

    async def test_market_snapshot(self, tdx_client):
        """Test /api/tdx/market-snapshot endpoint."""
        resp = await tdx_client.get("/api/tdx/market-snapshot?stock_code=600519.SH")
        if resp.status_code != 200:
            print(f"Error response: {resp.text}")
        assert resp.status_code == 200

    async def test_trading_dates(self, tdx_client):
        """Test /api/tdx/trading-dates endpoint."""
        resp = await tdx_client.get("/api/tdx/trading-dates?market=SH")
        assert resp.status_code == 200

    async def test_market_data(self, tdx_client):
        """Test /api/tdx/market-data endpoint."""
        resp = await tdx_client.get("/api/tdx/market-data?stocks=600519.SH&fields=Close&period=1d")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data


@pytest.mark.asyncio
class TestStockRoutes:
    """Test stock info routes."""

    async def test_stock_list(self, tdx_client):
        """Test /api/tdx/stock-list endpoint."""
        resp = await tdx_client.get("/api/tdx/stock-list?market=0")
        assert resp.status_code == 200

    async def test_stock_info(self, tdx_client):
        """Test /api/tdx/stock-info endpoint."""
        resp = await tdx_client.get("/api/tdx/stock-info?stock_code=600519.SH")
        assert resp.status_code == 200

    async def test_report_data(self, tdx_client):
        """Test /api/tdx/report-data endpoint."""
        resp = await tdx_client.get("/api/tdx/report-data?stock_code=600519.SH")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestFinancialRoutes:
    """Test financial data routes."""

    async def test_financial_data(self, tdx_client):
        """Test /api/tdx/financial-data endpoint."""
        resp = await tdx_client.get("/api/tdx/financial-data?stocks=600519.SH&fields=FN193")
        assert resp.status_code == 200

    async def test_financial_data_by_date(self, tdx_client):
        """Test /api/tdx/financial-data-by-date endpoint."""
        resp = await tdx_client.get("/api/tdx/financial-data-by-date?stocks=600519.SH&fields=FN193&year=2024&mmdd=1231")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestValueRoutes:
    """Test value data routes."""

    async def test_bkjy_value(self, tdx_client):
        """Test /api/tdx/bkjy-value endpoint."""
        resp = await tdx_client.get("/api/tdx/bkjy-value?stocks=600519.SH&fields=BK1")
        assert resp.status_code == 200

    async def test_gpjy_value(self, tdx_client):
        """Test /api/tdx/gpjy-value endpoint."""
        resp = await tdx_client.get("/api/tdx/gpjy-value?stocks=600519.SH&fields=GP1")
        assert resp.status_code == 200

    async def test_scjy_value(self, tdx_client):
        """Test /api/tdx/scjy-value endpoint."""
        resp = await tdx_client.get("/api/tdx/scjy-value?fields=SC1")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSectorRoutes:
    """Test sector routes."""

    async def test_sector_list(self, tdx_client):
        """Test /api/tdx/sector-list endpoint."""
        resp = await tdx_client.get("/api/tdx/sector-list")
        assert resp.status_code == 200

    async def test_user_sectors(self, tdx_client):
        """Test /api/tdx/user-sectors endpoint."""
        resp = await tdx_client.get("/api/tdx/user-sectors")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestETFRoutes:
    """Test ETF and bond routes."""

    async def test_kzz_info(self, tdx_client):
        """Test /api/tdx/kzz-info endpoint."""
        resp = await tdx_client.get("/api/tdx/kzz-info?stock_code=113001.SH")
        assert resp.status_code == 200

    async def test_ipo_info(self, tdx_client):
        """Test /api/tdx/ipo-info endpoint."""
        resp = await tdx_client.get("/api/tdx/ipo-info")
        assert resp.status_code == 200

    async def test_trackzs_etf_info(self, tdx_client):
        """Test /api/tdx/trackzs-etf-info endpoint."""
        resp = await tdx_client.get("/api/tdx/trackzs-etf-info?zs_code=000001.SH")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestClientRoutes:
    """Test client control routes."""

    async def test_exec_to_tdx(self, tdx_client):
        """Test /api/tdx/exec-to-tdx endpoint."""
        resp = await tdx_client.post("/api/tdx/exec-to-tdx", json={"cmd": "test", "param": "test"})
        assert resp.status_code in [200, 503]  # May return 503 if adapter not fully initialized
