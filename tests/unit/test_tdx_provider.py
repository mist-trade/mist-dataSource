import asyncio
from typing import Any

import pytest

from src.core.config import settings
from src.datasource.tdx.provider import TdxDatasourceProvider, TdxFormulaTimeoutError

REQUIRED_MARKET_DATA_FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]


class FakeTdxHttpClient:
    def __init__(self, responses: dict[str, Any] | None = None, error: Exception | None = None):
        self.responses = responses or {}
        self.error = error
        self.calls: list[tuple[str, dict[str, Any] | list[Any] | None]] = []
        self.closed = False

    async def call(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> Any:
        self.calls.append((method, params))
        if self.error is not None:
            raise self.error
        return self.responses[method]

    async def aclose(self) -> None:
        self.closed = True


class SlowTdxHttpClient(FakeTdxHttpClient):
    async def call(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> Any:
        self.calls.append((method, params))
        await asyncio.sleep(0.05)
        return {}


def native_bar_rows() -> dict[str, Any]:
    return {
        "Open": {"600519.SH": {"2026-06-26T09:31:00": "10.1"}},
        "High": {"600519.SH": {"2026-06-26T09:31:00": "10.3"}},
        "Low": {"600519.SH": {"2026-06-26T09:31:00": "10.0"}},
        "Close": {"600519.SH": {"2026-06-26T09:31:00": "10.2"}},
        "Volume": {"600519.SH": {"2026-06-26T09:31:00": "1200"}},
        "Amount": {"600519.SH": {"2026-06-26T09:31:00": "12345.6"}},
    }


def native_bar_rows_with_extensions() -> dict[str, Any]:
    rows = native_bar_rows()
    rows["ForwardFactor"] = {"600519.SH": {"2026-06-26T09:31:00": "0.711862"}}
    rows["VolInStock"] = {"600519.SH": {"2026-06-26T09:31:00": "182942480"}}
    rows["UnreviewedProviderField"] = {"600519.SH": {"2026-06-26T09:31:00": "ignore-me"}}
    return rows


def native_snapshot() -> dict[str, Any]:
    return {
        "Now": "10.2",
        "Open": "10.1",
        "Max": "10.3",
        "Min": "10.0",
        "LastClose": "9.9",
        "Volume": "1200",
        "Amount": "12345.6",
        "asof": "2026-06-26T09:31:02",
    }


@pytest.mark.asyncio
async def test_get_bars_calls_tdx_market_data_and_returns_normalized_rows():
    fake_client = FakeTdxHttpClient({"get_market_data": native_bar_rows()})
    provider = TdxDatasourceProvider(fake_client)

    bars = await provider.get_bars(
        ["600519.SH"],
        period="1m",
        start_time=None,
        end_time=None,
        count=2,
    )

    assert fake_client.calls == [
        (
            "get_market_data",
            {
                "stock_list": ["600519.SH"],
                "field_list": REQUIRED_MARKET_DATA_FIELDS,
                "period": "1m",
                "start_time": None,
                "end_time": None,
                "count": 2,
            },
        )
    ]
    assert len(bars) == 1
    assert bars[0].symbol == "600519.SH"
    assert bars[0].close == 10.2


@pytest.mark.asyncio
async def test_get_bars_passes_requested_fields_and_adjustment_options():
    requested_fields = ["Open", "Close", "ForwardFactor", "VolInStock"]
    fake_client = FakeTdxHttpClient({"get_market_data": native_bar_rows_with_extensions()})
    provider = TdxDatasourceProvider(fake_client)

    bars = await provider.get_bars(
        ["600519.SH"],
        period="1d",
        start_time="2026-06-01T00:00:00+08:00",
        end_time="2026-06-26",
        count=20,
        fields=requested_fields,
        dividend_type="none",
        fill_data=False,
    )

    assert fake_client.calls == [
        (
            "get_market_data",
            {
                "stock_list": ["600519.SH"],
                "field_list": requested_fields,
                "period": "1d",
                "start_time": "20260601",
                "end_time": "20260626",
                "count": 20,
                "dividend_type": "none",
                "fill_data": False,
            },
        )
    ]
    assert bars[0].forwardFactor == 0.711862
    assert bars[0].volInStock == 182942480.0


@pytest.mark.asyncio
async def test_get_bars_formats_intraday_filters_for_native_tdx():
    requested_fields = ["Open", "Close"]
    fake_client = FakeTdxHttpClient({"get_market_data": native_bar_rows()})
    provider = TdxDatasourceProvider(fake_client)

    await provider.get_bars(
        ["600519.SH"],
        period="1m",
        start_time="2026-06-26T09:30:00+08:00",
        end_time="2026-06-26T15:00:00+08:00",
        count=20,
        fields=requested_fields,
    )

    assert fake_client.calls[0][1]["period"] == "1m"
    assert fake_client.calls[0][1]["start_time"] == "20260626"
    assert fake_client.calls[0][1]["end_time"] == "20260626"


@pytest.mark.asyncio
async def test_get_bars_raises_native_tdx_errors():
    fake_client = FakeTdxHttpClient({"get_market_data": {"ErrorId": "5", "Error": "period error"}})
    provider = TdxDatasourceProvider(fake_client)

    with pytest.raises(Exception) as exc:
        await provider.get_bars(
            ["600519.SH"],
            period="60m",
            start_time="2026-06-26T09:30:00+08:00",
            end_time="2026-06-26T15:00:00+08:00",
            count=20,
        )

    assert exc.value.code == "TDX_NATIVE_ERROR"
    assert exc.value.details["nativeErrorId"] == "5"


@pytest.mark.asyncio
async def test_get_bars_accepts_value_wrapper_array_shape():
    fake_client = FakeTdxHttpClient(
        {
            "get_market_data": {
                "ErrorId": 0,
                "Value": {
                    "600519.SH": {
                        "Date": ["20260626"],
                        "Time": ["093100"],
                        "Open": ["10.1"],
                        "High": ["10.3"],
                        "Low": ["10.0"],
                        "Close": ["10.2"],
                        "Volume": ["1200"],
                        "Amount": ["12345.6"],
                    }
                },
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    bars = await provider.get_bars(
        ["600519.SH"],
        period="1m",
        start_time=None,
        end_time=None,
        count=1,
    )

    assert len(bars) == 1
    assert bars[0].barTime == "2026-06-26T09:31:00+08:00"
    assert bars[0].open == 10.1
    assert bars[0].close == 10.2


@pytest.mark.asyncio
async def test_get_bars_accepts_symbol_wrapper_array_shape():
    fake_client = FakeTdxHttpClient(
        {
            "get_market_data": {
                "600519.SH": {
                    "Date": ["20260626"],
                    "Time": ["093100"],
                    "Open": ["10.1"],
                    "High": ["10.3"],
                    "Low": ["10.0"],
                    "Close": ["10.2"],
                    "Volume": ["1200"],
                    "Amount": ["12345.6"],
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    bars = await provider.get_bars(
        ["600519.SH"],
        period="1m",
        start_time=None,
        end_time=None,
        count=1,
    )

    assert len(bars) == 1
    assert bars[0].barTime == "2026-06-26T09:31:00+08:00"
    assert bars[0].open == 10.1
    assert bars[0].close == 10.2


@pytest.mark.asyncio
async def test_provider_facade_exposes_representative_product_debug_and_lifecycle_methods():
    fake_client = FakeTdxHttpClient(
        {
            "get_market_snapshot": native_snapshot(),
            "get_financial_data": {
                "Value": {
                    "600519.SH": {
                        "FN193": "162.47",
                        "announce_time": "20250331",
                        "tag_time": "20241231",
                    }
                }
            },
            "get_sector_list": {
                "ErrorId": "0",
                "Value": [{"Code": "880081.SH", "Name": "通达信88"}],
            },
            "formula_format_data": {
                "Value": {
                    "688318.SH": [{"Close": "144.4"}],
                }
            },
            "raw_debug": {"ok": True},
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    financial = await provider.get_financial_data(
        ["600519.SH"],
        ["FN193"],
        "20250101",
        "20251231",
        "tag_time",
    )
    sector = (await provider.get_sector_list(1))[0]
    formula = await provider.format_formula_data({"688318.SH": [{"Close": 144.4}]})
    raw = await provider.raw_call("raw_debug", {"x": 1})
    health = await provider.health()
    await provider.aclose()

    assert financial[0]["field"] == "FN193"
    assert sector["code"] == "880081.SH"
    assert formula[0]["symbol"] == "688318.SH"
    assert raw == {"ok": True}
    assert health == {"tdxHttpReachable": True, "lastError": None}
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_raw_call_proxies_exact_method_and_params():
    fake_client = FakeTdxHttpClient({"some_method": {"ok": True}})
    provider = TdxDatasourceProvider(fake_client)

    result = await provider.raw_call("some_method", {"x": 1})

    assert result == {"ok": True}
    assert fake_client.calls == [("some_method", {"x": 1})]


@pytest.mark.asyncio
async def test_get_sector_members_calls_tdx_sector_method_and_returns_normalized_symbols():
    fake_client = FakeTdxHttpClient({"get_stock_list_in_sector": ["SH600519", "000001.SZ"]})
    provider = TdxDatasourceProvider(fake_client)

    members = await provider.get_sector_members("通达信88")

    assert members == ["600519.SH", "000001.SZ"]
    assert fake_client.calls == [
        (
            "get_stock_list_in_sector",
            {
                "block_code": "通达信88",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_sector_members_accepts_tdx_http_value_wrapper():
    fake_client = FakeTdxHttpClient(
        {
            "get_stock_list_in_sector": {
                "ErrorId": "0",
                "Value": ["600519.SH", "000001.SZ"],
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    members = await provider.get_sector_members("通达信88")

    assert members == ["600519.SH", "000001.SZ"]


@pytest.mark.asyncio
async def test_get_sector_list_calls_tdx_sector_list_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_sector_list": {
                "ErrorId": "0",
                "Value": [{"Code": "880081.SH", "Name": "通达信88"}],
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    sectors = await provider.get_sector_list(1)

    assert sectors[0]["code"] == "880081.SH"
    assert sectors[0]["name"] == "通达信88"
    assert fake_client.calls == [("get_sector_list", {"list_type": 1})]


@pytest.mark.asyncio
async def test_get_trading_dates_calls_tdx_calendar_method():
    fake_client = FakeTdxHttpClient(
        {"get_trading_dates": {"ErrorId": "0", "Value": ["2026-06-25", "2026-06-26"]}}
    )
    provider = TdxDatasourceProvider(fake_client)

    dates = await provider.get_trading_dates("SH", count=2)

    assert dates == ["2026-06-25", "2026-06-26"]
    assert fake_client.calls == [
        (
            "get_trading_dates",
            {
                "market": "SH",
                "start_time": "",
                "end_time": "",
                "count": 2,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_trading_dates_normalizes_tdx_date_field():
    fake_client = FakeTdxHttpClient(
        {"get_trading_dates": {"ErrorId": "0", "Date": ["20260625", "20260626"]}}
    )
    provider = TdxDatasourceProvider(fake_client)

    dates = await provider.get_trading_dates("SH", count=2)

    assert dates == ["2026-06-25", "2026-06-26"]


@pytest.mark.asyncio
async def test_get_securities_calls_tdx_stock_list_method():
    fake_client = FakeTdxHttpClient(
        {"get_stock_list": {"Value": [{"Code": "SH600519", "Name": "贵州茅台"}]}}
    )
    provider = TdxDatasourceProvider(fake_client)

    securities = await provider.get_securities("5")

    assert securities[0]["symbol"] == "600519.SH"
    assert securities[0]["name"] == "贵州茅台"
    assert fake_client.calls == [("get_stock_list", {"market": "5", "list_type": 1})]


@pytest.mark.asyncio
async def test_get_security_info_combines_stock_and_more_info():
    fake_client = FakeTdxHttpClient(
        {
            "get_stock_info": {"Name": "贵州茅台", "Market": "SH"},
            "get_more_info": {"Industry": "白酒"},
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    securities = await provider.get_security_info(["600519.SH"])

    assert securities[0]["symbol"] == "600519.SH"
    assert securities[0]["name"] == "贵州茅台"
    assert securities[0]["more"] == {"Industry": "白酒"}
    assert fake_client.calls == [
        ("get_stock_info", {"stock_code": "600519.SH"}),
        ("get_more_info", {"stock_code": "600519.SH", "field_list": []}),
    ]


@pytest.mark.asyncio
async def test_get_price_volume_calls_tdx_pricevol_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_pricevol": {
                "Value": {
                    "600519.SH": {
                        "Now": "1168.63",
                        "Volume": "1000",
                        "Amount": "1168630",
                    }
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_price_volume(["600519.SH"], fields=["price", "volume"])

    assert items[0]["symbol"] == "600519.SH"
    assert items[0]["price"] == 1168.63
    assert items[0]["volume"] == 1000.0
    assert fake_client.calls == [
        (
            "get_pricevol",
            {
                "stock_list": ["600519.SH"],
                "field_list": ["price", "volume"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_price_volume_raises_when_requested_symbol_is_missing():
    fake_client = FakeTdxHttpClient(
        {
            "get_pricevol": {
                "Value": {
                    "000001.SZ": {
                        "Now": "12.3",
                        "Volume": "1000",
                    }
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    with pytest.raises(Exception) as exc_info:
        await provider.get_price_volume(["600519.SH"], fields=["price", "volume"])

    assert exc_info.value.code == "TDX_SYMBOL_NOT_FOUND"
    assert exc_info.value.details["symbol"] == "600519.SH"


@pytest.mark.asyncio
async def test_get_security_relations_calls_tdx_relation_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_relation": {
                "Value": {
                    "RelatedSectors": [
                        {"Code": "880081.SH", "Name": "通达信88", "Type": "industry"}
                    ]
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    relations = await provider.get_security_relations("600519.SH")

    assert relations == [
        {
            "symbol": "600519.SH",
            "category": "industry",
            "code": "880081.SH",
            "name": "通达信88",
            "provider": "tdx",
            "raw": {"Code": "880081.SH", "Name": "通达信88", "Type": "industry"},
        }
    ]
    assert fake_client.calls == [("get_relation", {"stock_code": "600519.SH"})]


@pytest.mark.asyncio
async def test_get_ipo_info_calls_tdx_ipo_method_and_normalizes_items():
    fake_client = FakeTdxHttpClient(
        {
            "get_ipo_info": {
                "Value": [
                    {
                        "code": "301036",
                        "name": "双乐转债",
                        "SGCode": "371036",
                        "SGDate": "20251226",
                        "SGPrice": "100.00",
                    }
                ]
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_ipo_info(ipo_type=2, ipo_date=1)

    assert items[0]["code"] == "301036"
    assert items[0]["subscribeCode"] == "371036"
    assert items[0]["subscribeDate"] == "20251226"
    assert items[0]["issuePrice"] == 100.0
    assert fake_client.calls == [("get_ipo_info", {"ipo_type": 2, "ipo_date": 1})]


@pytest.mark.asyncio
async def test_get_share_capital_calls_tdx_gb_info_method():
    fake_client = FakeTdxHttpClient(
        {"get_gb_info": {"Value": [{"Date": 20250101, "Zgb": "182942480", "Ltgb": "182942480"}]}}
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_share_capital("600519.SH", ["20250101"], 1)

    assert items[0]["symbol"] == "600519.SH"
    assert items[0]["date"] == "20250101"
    assert items[0]["totalShareCapital"] == 182942480.0
    assert items[0]["floatShareCapital"] == 182942480.0
    assert fake_client.calls == [
        (
            "get_gb_info",
            {
                "stock_code": "600519.SH",
                "date_list": ["20250101"],
                "count": 1,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_share_capital_by_date_calls_tdx_gb_info_by_date_method():
    fake_client = FakeTdxHttpClient(
        {"get_gb_info_by_date": {"Value": [{"Date": "20250101", "Zgb": 1, "Ltgb": 2}]}}
    )
    provider = TdxDatasourceProvider(fake_client)

    await provider.get_share_capital_by_date("600519.SH", "20250101", "20250601")

    assert fake_client.calls == [
        (
            "get_gb_info_by_date",
            {
                "stock_code": "600519.SH",
                "start_date": "20250101",
                "end_date": "20250601",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_dividend_factors_calls_tdx_divid_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_divid_factors": {
                "Value": [
                    {
                        "Date": "20250101",
                        "Type": "1",
                        "Bonus": "1.23",
                        "ShareBonus": "0.5",
                    }
                ]
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_dividend_factors("600519.SH", "20250101", "20251231")

    assert items[0]["symbol"] == "600519.SH"
    assert items[0]["bonus"] == 1.23
    assert items[0]["shareBonus"] == 0.5
    assert fake_client.calls == [
        (
            "get_divid_factors",
            {
                "stock_code": "600519.SH",
                "start_time": "20250101",
                "end_time": "20251231",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_convertible_bond_info_calls_selected_tdx_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_kzz_info": {
                "Value": {
                    "KZZCode": "123039",
                    "HSCode": "300577",
                    "ZGPrice": "29.15",
                    "KZZPrice": "120.50",
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_convertible_bond_info(
        "123039.SZ",
        fields=["KZZCode", "HSCode"],
        native_method="get_kzz_info",
    )

    assert items[0]["symbol"] == "123039.SZ"
    assert items[0]["bondCode"] == "123039"
    assert items[0]["underlyingSymbol"] == "300577"
    assert items[0]["convertPrice"] == 29.15
    assert fake_client.calls == [
        (
            "get_kzz_info",
            {
                "stock_code": "123039.SZ",
                "field_list": ["KZZCode", "HSCode"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_tracking_etfs_calls_tdx_trackzs_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_trackzs_etf_info": {
                "Value": [{"Code": "510300.SH", "Name": "沪深300ETF", "NowPrice": "4.21"}]
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_tracking_etfs("950162.CSI")

    assert items[0]["indexSymbol"] == "950162.CSI"
    assert items[0]["symbol"] == "510300.SH"
    assert items[0]["price"] == 4.21
    assert fake_client.calls == [("get_trackzs_etf_info", {"zs_code": "950162.CSI"})]


@pytest.mark.asyncio
async def test_get_financial_data_calls_tdx_method_and_flattens_fields():
    fake_client = FakeTdxHttpClient(
        {
            "get_financial_data": {
                "Value": {
                    "600519.SH": {
                        "FN193": "162.47",
                        "FN194": "69.67",
                        "announce_time": "20250331",
                        "tag_time": "20241231",
                    }
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_financial_data(
        ["600519.SH"],
        ["FN193", "FN194"],
        "20250101",
        "20251231",
        "tag_time",
    )

    assert items[0]["symbol"] == "600519.SH"
    assert items[0]["field"] == "FN193"
    assert items[0]["value"] == 162.47
    assert items[0]["announceTime"] == "20250331"
    assert items[0]["tagTime"] == "20241231"
    assert items[1]["field"] == "FN194"
    assert fake_client.calls == [
        (
            "get_financial_data",
            {
                "stock_list": ["600519.SH"],
                "field_list": ["FN193", "FN194"],
                "start_time": "20250101",
                "end_time": "20251231",
                "report_type": "tag_time",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_financial_data_by_date_calls_tdx_date_method():
    fake_client = FakeTdxHttpClient(
        {
            "get_financial_data_by_date": {
                "Value": {
                    "600519.SH": {
                        "FN193": "162.47",
                        "tag_time": "20241231",
                    }
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_financial_data_by_date(["600519.SH"], ["FN193"], 0, 0)

    assert items[0]["symbol"] == "600519.SH"
    assert items[0]["value"] == 162.47
    assert fake_client.calls == [
        (
            "get_financial_data_by_date",
            {
                "stock_list": ["600519.SH"],
                "field_list": ["FN193"],
                "year": 0,
                "mmdd": 0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_single_finance_values_calls_gp_one_data_and_flattens_fields():
    fake_client = FakeTdxHttpClient(
        {
            "get_gp_one_data": {
                "Value": {
                    "GO1": {"688318.SH": "107.41"},
                    "GO2": {"688318.SH": "3.12"},
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_single_finance_values(["688318.SH"], ["GO1", "GO2"])

    assert items == [
        {
            "symbol": "688318.SH",
            "field": "GO1",
            "value": 107.41,
            "provider": "tdx",
            "raw": {"GO1": {"688318.SH": "107.41"}, "GO2": {"688318.SH": "3.12"}},
        },
        {
            "symbol": "688318.SH",
            "field": "GO2",
            "value": 3.12,
            "provider": "tdx",
            "raw": {"GO1": {"688318.SH": "107.41"}, "GO2": {"688318.SH": "3.12"}},
        },
    ]
    assert fake_client.calls == [
        (
            "get_gp_one_data",
            {
                "stock_list": ["688318.SH"],
                "table_list": ["GO1", "GO2"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_single_finance_values_accepts_symbol_first_tdx_shape():
    fake_client = FakeTdxHttpClient(
        {
            "get_gp_one_data": {
                "ErrorId": "0",
                "Value": {
                    "688318.SH": {
                        "GO1": "0.00",
                    }
                },
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_single_finance_values(["688318.SH"], ["GO1"])

    assert items == [
        {
            "symbol": "688318.SH",
            "field": "GO1",
            "value": 0.0,
            "provider": "tdx",
            "raw": {"688318.SH": {"GO1": "0.00"}},
        }
    ]


@pytest.mark.asyncio
async def test_get_stock_trade_aggregate_calls_tdx_gpjy_value():
    fake_client = FakeTdxHttpClient(
        {
            "get_gpjy_value": {
                "Value": {
                    "688318.SH": {"GP3": [{"Date": "20250102", "Value": ["141405.89", "11113.00"]}]}
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_stock_trade_aggregate(
        ["688318.SH"],
        ["GP3"],
        "20250101",
        "20250102",
    )

    assert items[0]["scope"] == "stock"
    assert items[0]["code"] == "688318.SH"
    assert items[0]["field"] == "GP3"
    assert items[0]["date"] == "20250102"
    assert items[0]["values"] == [141405.89, 11113.0]
    assert fake_client.calls == [
        (
            "get_gpjy_value",
            {
                "stock_list": ["688318.SH"],
                "field_list": ["GP3"],
                "start_time": "20250101",
                "end_time": "20250102",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_stock_trade_aggregate_by_date_calls_tdx_gpjy_value_by_date():
    fake_client = FakeTdxHttpClient(
        {"get_gpjy_value_by_date": {"Value": {"688318.SH": {"GP1": ["24154", "0"]}}}}
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_stock_trade_aggregate_by_date(["688318.SH"], ["GP1"], 0, 0)

    assert items[0]["scope"] == "stock"
    assert items[0]["values"] == [24154.0, 0.0]
    assert fake_client.calls == [
        (
            "get_gpjy_value_by_date",
            {
                "stock_list": ["688318.SH"],
                "field_list": ["GP1"],
                "year": 0,
                "mmdd": 0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_sector_trade_aggregate_calls_tdx_bkjy_value():
    fake_client = FakeTdxHttpClient(
        {
            "get_bkjy_value": {
                "Value": {"880660.SH": {"BK5": [{"Date": "20250102", "Value": ["55.28", "55.50"]}]}}
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_sector_trade_aggregate(
        ["880660.SH"],
        ["BK5"],
        "20250101",
        "20250102",
    )

    assert items[0]["scope"] == "sector"
    assert items[0]["code"] == "880660.SH"
    assert items[0]["values"] == [55.28, 55.5]
    assert fake_client.calls == [
        (
            "get_bkjy_value",
            {
                "stock_list": ["880660.SH"],
                "field_list": ["BK5"],
                "start_time": "20250101",
                "end_time": "20250102",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_sector_trade_aggregate_by_date_calls_tdx_bkjy_value_by_date():
    fake_client = FakeTdxHttpClient(
        {"get_bkjy_value_by_date": {"Value": {"880660.SH": {"BK9": ["3", "31"]}}}}
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_sector_trade_aggregate_by_date(["880660.SH"], ["BK9"], 0, 0)

    assert items[0]["scope"] == "sector"
    assert items[0]["values"] == [3.0, 31.0]
    assert fake_client.calls == [
        (
            "get_bkjy_value_by_date",
            {
                "stock_list": ["880660.SH"],
                "field_list": ["BK9"],
                "year": 0,
                "mmdd": 0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_market_trade_aggregate_calls_tdx_scjy_value():
    fake_client = FakeTdxHttpClient(
        {
            "get_scjy_value": {
                "Value": {"SC1": [{"Date": "20250102", "Value": ["184712288", "999820.06"]}]}
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_market_trade_aggregate(["SC1"], "20250101", "20250102")

    assert items[0]["scope"] == "market"
    assert items[0]["code"] is None
    assert items[0]["field"] == "SC1"
    assert items[0]["date"] == "20250102"
    assert items[0]["values"] == [184712288.0, 999820.06]
    assert fake_client.calls == [
        (
            "get_scjy_value",
            {
                "field_list": ["SC1"],
                "start_time": "20250101",
                "end_time": "20250102",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_market_trade_aggregate_by_date_calls_tdx_scjy_value_by_date():
    fake_client = FakeTdxHttpClient(
        {"get_scjy_value_by_date": {"Value": {"SC10": ["0", "181415.13"]}}}
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_market_trade_aggregate_by_date(["SC10"], 0, 0)

    assert items[0]["scope"] == "market"
    assert items[0]["values"] == [0.0, 181415.13]
    assert fake_client.calls == [
        (
            "get_scjy_value_by_date",
            {
                "field_list": ["SC10"],
                "year": 0,
                "mmdd": 0,
            },
        )
    ]


def test_report_data_is_not_a_normalized_provider_method():
    provider = TdxDatasourceProvider(FakeTdxHttpClient({}))

    assert not hasattr(provider, "get_report_data")


@pytest.mark.asyncio
async def test_format_formula_data_calls_tdx_formula_format_data():
    fake_client = FakeTdxHttpClient(
        {
            "formula_format_data": {
                "Value": {
                    "688318.SH": [{"Close": "144.4"}],
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.format_formula_data({"688318.SH": [{"Close": 144.4}]})

    assert items == [
        {
            "symbol": "688318.SH",
            "rows": [{"Close": "144.4"}],
            "provider": "tdx",
            "raw": [{"Close": "144.4"}],
        }
    ]
    assert fake_client.calls == [
        (
            "formula_format_data",
            {
                "data_dict": {"688318.SH": [{"Close": 144.4}]},
            },
        )
    ]


@pytest.mark.asyncio
async def test_set_formula_data_calls_tdx_formula_set_data():
    fake_client = FakeTdxHttpClient({"formula_set_data": {"Value": {"Result": "OK"}}})
    provider = TdxDatasourceProvider(fake_client)

    result = await provider.set_formula_data(
        {
            "stockCode": "688318.SH",
            "stockPeriod": "1d",
            "stockData": [{"Close": 144.4}],
            "count": 1,
            "dividendType": 1,
            "timeoutMs": 10000,
        }
    )

    assert result["message"] == "OK"
    assert result["provider"] == "tdx"
    assert fake_client.calls == [
        (
            "formula_set_data",
            {
                "stock_code": "688318.SH",
                "stock_period": "1d",
                "stock_data": [{"Close": 144.4}],
                "count": 1,
                "dividend_type": 1,
            },
        )
    ]


@pytest.mark.asyncio
async def test_set_formula_data_info_calls_tdx_formula_set_data_info():
    fake_client = FakeTdxHttpClient({"formula_set_data_info": {"Value": True}})
    provider = TdxDatasourceProvider(fake_client)

    result = await provider.set_formula_data_info(
        {
            "stockCode": "688318.SH",
            "stockPeriod": "1d",
            "startTime": "20250101",
            "endTime": "20250102",
            "count": 2,
            "dividendType": 0,
            "timeoutMs": 10000,
        }
    )

    assert result["ok"] is True
    assert fake_client.calls == [
        (
            "formula_set_data_info",
            {
                "stock_code": "688318.SH",
                "stock_period": "1d",
                "start_time": "20250101",
                "end_time": "20250102",
                "count": 2,
                "dividend_type": 0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_formula_data_calls_tdx_formula_get_data():
    fake_client = FakeTdxHttpClient(
        {"formula_get_data": {"Value": {"688318.SH": [{"Close": "144.4"}]}}}
    )
    provider = TdxDatasourceProvider(fake_client)

    item = await provider.get_formula_data()

    assert item["symbol"] == "688318.SH"
    assert item["rows"] == [{"Close": "144.4"}]
    assert fake_client.calls == [("formula_get_data", {})]


@pytest.mark.asyncio
async def test_formula_methods_default_to_configured_timeout(monkeypatch):
    monkeypatch.setattr(settings.tdx, "formula_timeout_ms", 1)
    provider = TdxDatasourceProvider(SlowTdxHttpClient({"formula_get_data": {}}))

    with pytest.raises(TdxFormulaTimeoutError) as exc_info:
        await provider.get_formula_data()

    assert exc_info.value.details["timeoutMs"] == 1


def test_formula_operation_result_model_serializes_result_contract() -> None:
    from src.datasource.tdx.models import TdxFormulaOperationResult

    result = TdxFormulaOperationResult(ok=True, message="OK", raw={"Result": "OK"})

    assert result.model_dump(by_alias=True) == {
        "ok": True,
        "message": "OK",
        "provider": "tdx",
        "raw": {"Result": "OK"},
    }


@pytest.mark.asyncio
async def test_get_formula_list_calls_tdx_formula_get_all():
    fake_client = FakeTdxHttpClient(
        {
            "formula_get_all": {
                "Value": [{"FormulaCode": "MACD", "FormulaName": "平滑异同平均线", "Type": 0}]
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    items = await provider.get_formula_list(0)

    assert items[0]["code"] == "MACD"
    assert items[0]["name"] == "平滑异同平均线"
    assert fake_client.calls == [("formula_get_all", {"formula_type": 0})]


@pytest.mark.asyncio
async def test_get_formula_info_calls_tdx_formula_get_info():
    fake_client = FakeTdxHttpClient(
        {
            "formula_get_info": {
                "Value": {
                    "FormulaCode": "MACD",
                    "FormulaName": "平滑异同平均线",
                    "Params": [{"Name": "SHORT", "Default": 12}],
                    "Lines": [{"Name": "DIF"}],
                }
            }
        }
    )
    provider = TdxDatasourceProvider(fake_client)

    item = await provider.get_formula_info(0, "MACD")

    assert item["code"] == "MACD"
    assert item["params"][0]["Name"] == "SHORT"
    assert fake_client.calls == [("formula_get_info", {"formula_type": 0, "formula_code": "MACD"})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expected_method", "expected_params"),
    [
        (
            "zb",
            "formula_zb",
            {"formula_name": "MACD", "formula_arg": "12,26,9", "xsflag": 8},
        ),
        (
            "xg",
            "formula_xg",
            {"formula_name": "UPN", "formula_arg": "3"},
        ),
        (
            "exp",
            "formula_exp",
            {"formula_name": "CCI", "formula_arg": "12"},
        ),
    ],
)
async def test_execute_formula_calls_selected_tdx_method(
    kind: str,
    expected_method: str,
    expected_params: dict[str, Any],
):
    fake_client = FakeTdxHttpClient({expected_method: {"Value": {"DIF": ["0.1"]}}})
    provider = TdxDatasourceProvider(fake_client)

    result = await provider.execute_formula(
        kind,
        expected_params["formula_name"],
        expected_params["formula_arg"],
        expected_params.get("xsflag"),
        timeout_ms=10000,
    )

    assert result["kind"] == kind
    assert result["raw"] == {"DIF": ["0.1"]}
    assert fake_client.calls == [(expected_method, expected_params)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "expected_method"),
    [
        ("xg", "formula_process_mul_xg"),
        ("zb", "formula_process_mul_zb"),
        ("exp", "formula_process_mul_exp"),
    ],
)
async def test_execute_formula_batch_calls_selected_tdx_method(kind: str, expected_method: str):
    fake_client = FakeTdxHttpClient({expected_method: {"Value": [{"Code": "688318.SH"}]}})
    provider = TdxDatasourceProvider(fake_client)

    result = await provider.execute_formula_batch(
        kind,
        {
            "formulaName": "UPN",
            "formulaArg": "3",
            "returnCount": 1,
            "returnDate": False,
            "stockList": ["688318.SH"],
            "stockPeriod": "1d",
            "startTime": "",
            "endTime": "",
            "count": 2,
            "dividendType": 0,
            "timeoutMs": 10000,
        },
    )

    assert result["kind"] == kind
    assert result["items"] == [{"Code": "688318.SH"}]
    assert fake_client.calls == [
        (
            expected_method,
            {
                "formula_name": "UPN",
                "formula_arg": "3",
                "return_count": 1,
                "return_date": False,
                "stock_list": ["688318.SH"],
                "stock_period": "1d",
                "start_time": "",
                "end_time": "",
                "count": 2,
                "dividend_type": 0,
            },
        )
    ]


@pytest.mark.asyncio
async def test_execute_formula_timeout_raises_stable_error():
    fake_client = SlowTdxHttpClient({})
    provider = TdxDatasourceProvider(fake_client)

    with pytest.raises(Exception) as exc_info:
        await provider.execute_formula("xg", "UPN", "3", None, timeout_ms=1)

    assert exc_info.value.code == "FORMULA_TIMEOUT"
    assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_call_formula_passes_exact_formula_method_with_args_and_context():
    fake_response = {"value": 10.2}
    fake_client = FakeTdxHttpClient({"formula_exp": fake_response})
    provider = TdxDatasourceProvider(fake_client)

    result = await provider.call_formula(
        "formula_exp",
        {"exp": "CLOSE"},
        {"symbol": "600519.SH"},
    )

    assert result == fake_response
    assert fake_client.calls == [
        (
            "formula_exp",
            {
                "args": {"exp": "CLOSE"},
                "context": {"symbol": "600519.SH"},
            },
        )
    ]


@pytest.mark.asyncio
async def test_collect_recent_bars_uses_count_without_date_range():
    fake_client = FakeTdxHttpClient({"get_market_data": native_bar_rows()})
    provider = TdxDatasourceProvider(fake_client)

    bars = await provider.collect_recent_bars(["600519.SH"], period="1m", count=2)

    assert fake_client.calls == [
        (
            "get_market_data",
            {
                "stock_list": ["600519.SH"],
                "field_list": REQUIRED_MARKET_DATA_FIELDS,
                "period": "1m",
                "start_time": None,
                "end_time": None,
                "count": 2,
            },
        )
    ]
    assert bars[0].symbol == "600519.SH"


@pytest.mark.asyncio
async def test_health_reports_reachability_without_live_network_when_fake_client_is_injected():
    fake_client = FakeTdxHttpClient({"get_market_snapshot": native_snapshot()})
    provider = TdxDatasourceProvider(fake_client)

    health = await provider.health()

    assert health["tdxHttpReachable"] is True
    assert health["lastError"] is None
    assert fake_client.calls == [
        (
            "get_market_snapshot",
            {
                "stock_code": "600519.SH",
                "field_list": [],
            },
        )
    ]


@pytest.mark.asyncio
async def test_health_reports_last_error_from_fake_client():
    fake_client = FakeTdxHttpClient(error=RuntimeError("boom"))
    provider = TdxDatasourceProvider(fake_client)

    health = await provider.health()

    assert health["tdxHttpReachable"] is False
    assert health["lastError"] == "boom"


@pytest.mark.asyncio
async def test_aclose_closes_underlying_client():
    fake_client = FakeTdxHttpClient()
    provider = TdxDatasourceProvider(fake_client)

    await provider.aclose()

    assert fake_client.closed is True
