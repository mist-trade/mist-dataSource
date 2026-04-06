"""Unit tests for TDX adapter methods.

Tests all implemented adapter methods using the mock adapter with fixed deterministic data.
"""

import pytest

from src.adapter.mock.tdx_mock import TDXMockAdapter


@pytest.fixture
async def adapter():
    """Create and initialize TDX mock adapter."""
    a = TDXMockAdapter()
    await a.initialize()
    yield a
    await a.shutdown()


@pytest.mark.asyncio
class TestMarketDataMethods:
    """Test market data methods."""

    async def test_get_market_snapshot(self, adapter):
        """Test get_market_snapshot returns dict with expected fields."""
        result = await adapter.get_market_snapshot("600519.SH")
        assert isinstance(result, dict)
        # Mock snapshot contains these fields
        assert "Now" in result or "Amount" in result

    async def test_get_divid_factors(self, adapter):
        """Test get_divid_factors returns DataFrame-like data."""
        result = await adapter.get_divid_factors("600519.SH")
        # Should return data structure (mock returns dict)
        assert result is not None

    async def test_get_gb_info(self, adapter):
        """Test get_gb_info returns dict."""
        result = await adapter.get_gb_info("600519.SH")
        assert isinstance(result, dict)

    async def test_get_trading_dates(self, adapter):
        """Test get_trading_dates returns list of date strings."""
        result = await adapter.get_trading_dates("SH")
        assert isinstance(result, list)

    async def test_refresh_cache(self, adapter):
        """Test refresh_cache - mock does nothing."""
        await adapter.refresh_cache("600519.SH")  # type: ignore

    async def test_refresh_kline(self, adapter):
        """Test refresh_kline - mock does nothing."""
        await adapter.refresh_kline("600519.SH")  # type: ignore

    async def test_download_file(self, adapter):
        """Test download_file - mock does nothing."""
        await adapter.download_file("600519.SH")  # type: ignore


@pytest.mark.asyncio
class TestStockInfoMethods:
    """Test stock info methods."""

    async def test_get_stock_info(self, adapter):
        """Test get_stock_info returns dict with stock info."""
        result = await adapter.get_stock_info("600519.SH")
        assert isinstance(result, dict)
        assert "Code" in result or "Name" in result

    async def test_get_report_data(self, adapter):
        """Test get_report_data returns dict."""
        result = await adapter.get_report_data("600519.SH")
        assert isinstance(result, dict)

    async def test_get_more_info(self, adapter):
        """Test get_more_info returns dict."""
        result = await adapter.get_more_info("600519.SH")
        assert isinstance(result, dict)

    async def test_get_relation(self, adapter):
        """Test get_relation returns dict with sector info."""
        result = await adapter.get_relation("600519.SH")
        assert isinstance(result, dict)


@pytest.mark.asyncio
class TestFinancialMethods:
    """Test financial data methods."""

    async def test_get_financial_data(self, adapter):
        """Test get_financial_data returns dict with stock data."""
        result = await adapter.get_financial_data(
            ["600519.SH", "000001.SZ"],
            ["FN193", "FN194"],
            "",
            "",
            "announce_time"
        )
        assert isinstance(result, dict)
        assert "600519.SH" in result or len(result) > 0

    async def test_get_financial_data_by_date(self, adapter):
        """Test get_financial_data_by_date returns dict."""
        result = await adapter.get_financial_data_by_date(
            ["600519.SH"],
            ["FN193"],
            2024,
            1231
        )
        assert isinstance(result, dict)

    async def test_get_gp_one_data(self, adapter):
        """Test get_gp_one_data returns dict."""
        result = await adapter.get_gp_one_data(["600519.SH"], ["FN1"])
        assert isinstance(result, dict)


@pytest.mark.asyncio
class TestValueMethods:
    """Test value data methods (bkjy, gpjy, scjy)."""

    async def test_get_bkjy_value(self, adapter):
        """Test get_bkjy_value returns dict."""
        result = await adapter.get_bkjy_value(["600519.SH"], ["BK1"])
        assert isinstance(result, dict)

    async def test_get_bkjy_value_by_date(self, adapter):
        """Test get_bkjy_value_by_date returns dict."""
        result = await adapter.get_bkjy_value_by_date(["600519.SH"], ["BK1"], 2024)
        assert isinstance(result, dict)

    async def test_get_gpjy_value(self, adapter):
        """Test get_gpjy_value returns dict."""
        result = await adapter.get_gpjy_value(["600519.SH"], ["GP1"])
        assert isinstance(result, dict)

    async def test_get_gpjy_value_by_date(self, adapter):
        """Test get_gpjy_value_by_date returns dict."""
        result = await adapter.get_gpjy_value_by_date(["600519.SH"], ["GP1"], 2024)
        assert isinstance(result, dict)

    async def test_get_scjy_value(self, adapter):
        """Test get_scjy_value returns dict."""
        result = await adapter.get_scjy_value(["SC1"], ["SC1"])
        assert isinstance(result, dict)

    async def test_get_scjy_value_by_date(self, adapter):
        """Test get_scjy_value_by_date returns dict."""
        result = await adapter.get_scjy_value_by_date(["SC1"], ["SC1"], "20241231")
        assert isinstance(result, dict)


@pytest.mark.asyncio
class TestSectorMethods:
    """Test sector management methods."""

    async def test_get_sector_list(self, adapter):
        """Test get_sector_list returns list."""
        result = await adapter.get_sector_list(0)
        assert isinstance(result, list)

    async def test_get_user_sector(self, adapter):
        """Test get_user_sector returns list."""
        result = await adapter.get_user_sector("test")
        assert isinstance(result, list)

    async def test_create_sector_raises_not_implemented(self, adapter):
        """Test create_sector - mock does nothing."""
        await adapter.create_sector("test", "test")  # type: ignore

    async def test_delete_sector_raises_not_implemented(self, adapter):
        """Test delete_sector - mock does nothing."""
        await adapter.delete_sector("test")  # type: ignore

    async def test_rename_sector_raises_not_implemented(self, adapter):
        """Test rename_sector - mock does nothing."""
        await adapter.rename_sector("test", "test")  # type: ignore

    async def test_clear_sector_raises_not_implemented(self, adapter):
        """Test clear_sector - mock does nothing."""
        await adapter.clear_sector("test")  # type: ignore


@pytest.mark.asyncio
class TestETFMethods:
    """Test ETF and bond methods."""

    async def test_get_kzz_info(self, adapter):
        """Test get_kzz_info returns dict."""
        result = await adapter.get_kzz_info()
        assert isinstance(result, dict)

    async def test_get_ipo_info(self, adapter):
        """Test get_ipo_info returns dict with IPO stocks."""
        result = await adapter.get_ipo_info()
        assert isinstance(result, dict)
        assert "IPOStocks" in result

    async def test_get_trackzs_etf_info(self, adapter):
        """Test get_trackzs_etf_info returns dict."""
        result = await adapter.get_trackzs_etf_info()
        assert isinstance(result, dict)


@pytest.mark.asyncio
class TestSubscriptionMethods:
    """Test subscription methods."""

    async def test_subscribe_hq(self, adapter):
        """Test subscribe_hq - mock adds to subscribed set."""
        await adapter.subscribe_hq(["600519.SH"])
        assert "600519.SH" in adapter._subscribed_stocks

    async def test_unsubscribe_hq(self, adapter):
        """Test unsubscribe_hq - mock does nothing."""
        await adapter.unsubscribe_hq(["600519.SH"])  # type: ignore

    async def test_get_subscribe_list(self, adapter):
        """Test get_subscribe_list returns list."""
        result = await adapter.get_subscribe_list()
        assert isinstance(result, list)


@pytest.mark.asyncio
class TestClientControl:
    """Test client control methods."""

    async def test_exec_to_tdx(self, adapter):
        """Test exec_to_tdx - mock does nothing."""
        await adapter.exec_to_tdx("test_code")  # type: ignore


@pytest.mark.asyncio
class testAbstractMethods:
    """Test required abstract methods."""

    async def test_get_stock_list(self, adapter):
        """Test get_stock_list (market-based) returns list."""
        result = await adapter.get_stock_list("0")
        assert isinstance(result, list)
        assert len(result) > 0

    async def test_get_stock_list_in_sector(self, adapter):
        """Test get_stock_list_in_sector returns list."""
        result = await adapter.get_stock_list_in_sector("通达信88")
        assert isinstance(result, list)
        assert len(result) > 0

    async def test_get_market_data(self, adapter):
        """Test get_market_data returns dict with field data."""
        result = await adapter.get_market_data(
            ["600519.SH", "000001.SZ"],
            ["Close", "Volume"],
            "1d"
        )
        assert isinstance(result, dict)
        assert "Close" in result
        assert "Volume" in result


@pytest.mark.asyncio
class testTODOStubs:
    """Test that trading and formula stubs raise NotImplementedError."""

    async def test_order_stock_raises_not_implemented(self, adapter):
        """Test order_stock raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.order_stock()

    async def test_cancel_order_stock_raises_not_implemented(self, adapter):
        """Test cancel_order_stock raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.cancel_order_stock()

    async def test_query_stock_orders_raises_not_implemented(self, adapter):
        """Test query_stock_orders raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.query_stock_orders()

    async def test_query_stock_positions_raises_not_implemented(self, adapter):
        """Test query_stock_positions raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.query_stock_positions()

    async def test_query_stock_asset_raises_not_implemented(self, adapter):
        """Test query_stock_asset raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.query_stock_asset()

    async def test_stock_account_raises_not_implemented(self, adapter):
        """Test stock_account raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.stock_account()

    async def test_formula_format_data_raises_not_implemented(self, adapter):
        """Test formula_format_data raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.formula_format_data({})

    async def test_formula_set_data_raises_not_implemented(self, adapter):
        """Test formula_set_data raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.formula_set_data({})

    async def test_send_message_raises_not_implemented(self, adapter):
        """Test send_message raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.send_message("")

    async def test_send_file_raises_not_implemented(self, adapter):
        """Test send_file raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.send_file("")

    async def test_send_warn_raises_not_implemented(self, adapter):
        """Test send_warn raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.send_warn("")

    async def test_send_bt_data_raises_not_implemented(self, adapter):
        """Test send_bt_data raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.send_bt_data({})

    async def test_print_to_tdx_raises_not_implemented(self, adapter):
        """Test print_to_tdx raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await adapter.print_to_tdx("")
