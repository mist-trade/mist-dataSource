"""Integration tests for QMT route endpoints.

Tests all HTTP endpoints against the QMT service using mock adapter.
"""

import pytest


@pytest.mark.asyncio
class TestMarketRoutes:
    """Test QMT market data routes."""

    async def test_stock_list_in_sector(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/stock-list-in-sector")
        assert resp.status_code == 200
        data = resp.json()
        assert "stocks" in data
        assert "count" in data

    async def test_market_data(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/market/market-data?stocks=600000.SH&fields=close&period=1d"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_local_data(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/market/local-data?stocks=600000.SH&fields=close&period=1d"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_full_tick(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/full-tick?codes=600000.SH")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_full_kline(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/market/full-kline?stocks=600000.SH&period=1m&count=1"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_divid_factors(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/divid-factors?stock_code=600000.SH")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_history_data(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/market/download-history-data",
            json={"stock_code": "600000.SH", "period": "1d"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_download_history_data2(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/market/download-history-data2",
            json={"stock_list": ["600000.SH"], "period": "1d"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_trading_dates(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/trading-dates?market=SH")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_trading_calendar(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/trading-calendar?market=SH")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_holidays(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/holidays")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_holiday_data(self, qmt_client):
        resp = await qmt_client.post("/api/qmt/market/download-holiday-data")
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_period_list(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/market/period-list")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data


@pytest.mark.asyncio
class TestStockRoutes:
    """Test QMT stock info routes."""

    async def test_instrument_detail(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/stock/instrument-detail?stock_code=600000.SH"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_instrument_type(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/stock/instrument-type?stock_code=600000.SH"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data


@pytest.mark.asyncio
class TestFinancialRoutes:
    """Test QMT financial data routes."""

    async def test_financial_data(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/financial/financial-data?stocks=600000.SH&tables=Balance"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_financial_data(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/financial/download-financial-data",
            json={"stock_list": ["600000.SH"]},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_download_financial_data2(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/financial/download-financial-data2",
            json={"stock_list": ["600000.SH"]},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"


@pytest.mark.asyncio
class TestSectorRoutes:
    """Test QMT sector management routes."""

    async def test_sector_list(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/sector/sector-list")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_sector_data(self, qmt_client):
        resp = await qmt_client.post("/api/qmt/sector/download-sector-data")
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_index_weight(self, qmt_client):
        resp = await qmt_client.get(
            "/api/qmt/sector/index-weight?index_code=000300.SH"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_index_weight(self, qmt_client):
        resp = await qmt_client.post("/api/qmt/sector/download-index-weight")
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_create_sector_folder(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/sector/create-sector-folder",
            json={"folder_name": "test_folder"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_create_sector(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/sector/create-sector",
            json={"sector_name": "test_sector"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_add_sector(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/sector/add-sector",
            json={"sector_name": "test_sector", "stock_list": ["600000.SH"]},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_remove_stock_from_sector(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/sector/remove-stock-from-sector",
            json={"sector_name": "test_sector", "stock_list": ["600000.SH"]},
        )
        assert resp.status_code == 200

    async def test_remove_sector(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/sector/remove-sector",
            json={"sector_name": "test_sector"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_reset_sector(self, qmt_client):
        resp = await qmt_client.post(
            "/api/qmt/sector/reset-sector",
            json={"sector_name": "test_sector", "stock_list": ["600000.SH"]},
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestEtfRoutes:
    """Test QMT ETF/bond/IPO routes."""

    async def test_cb_info(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/etf/cb-info?stock_code=113001.SH")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_cb_data(self, qmt_client):
        resp = await qmt_client.post("/api/qmt/etf/download-cb-data")
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"

    async def test_ipo_info(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/etf/ipo-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_etf_info(self, qmt_client):
        resp = await qmt_client.get("/api/qmt/etf/etf-info")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data

    async def test_download_etf_info(self, qmt_client):
        resp = await qmt_client.post("/api/qmt/etf/download-etf-info")
        assert resp.status_code == 200
        assert resp.json()["data"] == "ok"
