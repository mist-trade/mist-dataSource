import pandas as pd

from src.datasource.tdx.models import TdxBar, TdxBarQueryRequest, TdxSnapshot
from src.datasource.tdx.normalization import (
    native_value,
    normalize_native_key,
    normalize_number,
    normalize_optional_number,
    normalize_symbol,
    normalize_tdx_bar_rows,
    normalize_tdx_snapshot,
    to_tdx_code,
    to_tdx_http_code,
)


def test_normalize_symbol_accepts_tdx_prefix_and_market_suffix():
    assert normalize_symbol("SH600519") == "600519.SH"
    assert normalize_symbol("600519.SH") == "600519.SH"
    assert normalize_symbol("SZ000001") == "000001.SZ"
    assert normalize_symbol("000001.SZ") == "000001.SZ"


def test_to_tdx_code_returns_prefix_shape():
    assert to_tdx_code("600519.SH") == "SH600519"
    assert to_tdx_code("000001.SZ") == "SZ000001"


def test_to_tdx_http_code_returns_dotted_shape():
    assert to_tdx_http_code("SH600519") == "600519.SH"
    assert to_tdx_http_code("600519.SH") == "600519.SH"
    assert to_tdx_http_code("SZ000001") == "000001.SZ"


def test_normalize_number_coerces_strings_and_empty_values():
    assert normalize_number("12.30") == 12.3
    assert normalize_number(9) == 9.0
    assert normalize_number("") == 0.0
    assert normalize_number(None) == 0.0


def test_normalize_optional_number_treats_blank_provider_values_as_missing():
    assert normalize_optional_number("") is None
    assert normalize_optional_number("   ") is None
    assert normalize_optional_number(None) is None
    assert normalize_optional_number("12.30") == 12.3


def test_native_key_helpers_normalize_provider_field_variants():
    native = {
        "SG Code": "371036",
        "Formula_Code": "MACD",
        "last close": "9.9",
    }

    assert normalize_native_key("SG Code") == normalize_native_key("sg_code")
    assert native_value(native, "sg_code") == "371036"
    assert native_value(native, "formulaCode") == "MACD"
    assert native_value(native, "LastClose") == "9.9"


def test_tdx_bar_model_normalizes_naive_time_fields_to_beijing_iso():
    bar = TdxBar(
        symbol="600519.SH",
        period="1m",
        barTime="2026-06-26T09:31:00",
        open=10.1,
        high=10.3,
        low=10.0,
        close=10.2,
        volume=1200,
        amount=12345.6,
        provider="tdx",
        receivedAt="2026-06-26T09:31:02",
    )

    payload = bar.model_dump()

    assert payload["barTime"] == "2026-06-26T09:31:00+08:00"
    assert payload["receivedAt"] == "2026-06-26T09:31:02+08:00"


def test_tdx_snapshot_model_normalizes_naive_as_of_to_beijing_iso():
    snapshot = TdxSnapshot(
        symbol="600519.SH",
        last=10.2,
        open=10.1,
        high=10.3,
        low=10.0,
        lastClose=9.9,
        volume=1200,
        amount=12345.6,
        provider="tdx",
        asOf="2026-06-26T09:31:02",
    )

    payload = snapshot.model_dump()

    assert payload["asOf"] == "2026-06-26T09:31:02+08:00"
    assert payload["lastClose"] == 9.9


def test_tdx_bar_query_request_normalizes_naive_time_aliases_to_beijing_iso():
    request = TdxBarQueryRequest(
        symbols=["600519.SH"],
        period="1m",
        startTime="2026-06-26T09:30:00",
        endTime="2026-06-26T10:00:00",
    )

    payload = request.model_dump()

    assert payload["startTime"] == "2026-06-26T09:30:00+08:00"
    assert payload["endTime"] == "2026-06-26T10:00:00+08:00"


def test_tdx_bar_query_request_accepts_field_and_adjustment_aliases():
    request = TdxBarQueryRequest(
        symbols=["600519.SH"],
        period="1d",
        fields=["Open", "Close", "ForwardFactor", "VolInStock"],
        dividendType="none",
        fillData=False,
    )

    payload = request.model_dump()

    assert payload["fields"] == ["Open", "Close", "ForwardFactor", "VolInStock"]
    assert payload["dividendType"] == "none"
    assert payload["fillData"] is False


def test_normalize_bar_rows_outputs_iso_beijing_time_and_numbers():
    rows = normalize_tdx_bar_rows(
        symbol="SH600519",
        period="1m",
        native={
            "Open": {"SH600519": {"2026-06-26T09:31:00": "10.1"}},
            "High": {"SH600519": {"2026-06-26T09:31:00": "10.3"}},
            "Low": {"SH600519": {"2026-06-26T09:31:00": "10.0"}},
            "Close": {"SH600519": {"2026-06-26T09:31:00": "10.2"}},
            "Volume": {"SH600519": {"2026-06-26T09:31:00": "1200"}},
            "Amount": {"SH600519": {"2026-06-26T09:31:00": "12345.6"}},
        },
    )

    assert len(rows) == 1
    assert rows[0].symbol == "600519.SH"
    assert rows[0].barTime == "2026-06-26T09:31:00+08:00"
    assert rows[0].close == 10.2
    assert rows[0].provider == "tdx"


def test_normalize_bar_rows_accepts_tdx_http_value_wrapper_arrays():
    rows = normalize_tdx_bar_rows(
        symbol="600519.SH",
        period="1d",
        native={
            "ErrorId": "0",
            "Value": {
                "600519.SH": {
                    "Amount": ["586048.13", "592201.44"],
                    "Close": ["1212.10", "1168.63"],
                    "Date": ["20260625", "20260626"],
                    "High": ["1227.00", "1199.00"],
                    "Low": ["1200.00", "1168.10"],
                    "Open": ["1207.00", "1199.00"],
                    "Time": ["0", "0"],
                    "Volume": ["4844649.00", "5006647.00"],
                }
            },
        },
    )

    assert len(rows) == 2
    assert rows[0].symbol == "600519.SH"
    assert rows[0].barTime == "2026-06-25T00:00:00+08:00"
    assert rows[0].close == 1212.10
    assert rows[1].barTime == "2026-06-26T00:00:00+08:00"
    assert rows[1].close == 1168.63
    assert rows[1].amount == 592201.44


def test_normalize_bar_rows_preserves_named_tdx_extension_fields_without_raw_payload():
    rows = normalize_tdx_bar_rows(
        symbol="600519.SH",
        period="1d",
        native={
            "ErrorId": "0",
            "Value": {
                "600519.SH": {
                    "Date": ["20260626"],
                    "Time": ["0"],
                    "Open": ["1199.00"],
                    "High": ["1199.00"],
                    "Low": ["1168.10"],
                    "Close": ["1168.63"],
                    "Volume": ["5006647.00"],
                    "Amount": ["592201.44"],
                    "ForwardFactor": ["0.711862"],
                    "VolInStock": ["182942480"],
                    "UnreviewedProviderField": ["should-not-leak"],
                }
            },
        },
    )

    assert len(rows) == 1
    payload = rows[0].model_dump()
    assert payload["forwardFactor"] == 0.711862
    assert payload["volInStock"] == 182942480.0
    assert "raw" not in payload
    assert "UnreviewedProviderField" not in payload


def test_normalize_bar_rows_returns_empty_when_requested_symbol_is_missing():
    rows = normalize_tdx_bar_rows(
        symbol="SZ000001",
        period="1m",
        native={
            "Open": {"SH600519": {"2026-06-26T09:31:00": "10.1"}},
            "Close": {"SH600519": {"2026-06-26T09:31:00": "10.2"}},
        },
    )

    assert rows == []


def test_normalize_bar_rows_accepts_tdx_dataframe_field_values():
    native = {
        "Open": pd.DataFrame({"2026-06-26T09:31:00": [10.1]}, index=["SH600519"]),
        "High": pd.DataFrame({"2026-06-26T09:31:00": [10.3]}, index=["SH600519"]),
        "Low": pd.DataFrame({"2026-06-26T09:31:00": [10.0]}, index=["SH600519"]),
        "Close": pd.DataFrame({"2026-06-26T09:31:00": [10.2]}, index=["SH600519"]),
        "Volume": pd.DataFrame({"2026-06-26T09:31:00": [1200]}, index=["SH600519"]),
        "Amount": pd.DataFrame({"2026-06-26T09:31:00": [12345.6]}, index=["SH600519"]),
    }

    rows = normalize_tdx_bar_rows("600519.SH", "1m", native)

    assert len(rows) == 1
    assert rows[0].symbol == "600519.SH"
    assert rows[0].barTime == "2026-06-26T09:31:00+08:00"
    assert rows[0].close == 10.2


def test_normalize_snapshot_maps_native_fields():
    snapshot = normalize_tdx_snapshot(
        "SH600519",
        {
            "Now": "10.2",
            "Open": "10.1",
            "Max": "10.3",
            "Min": "10.0",
            "LastClose": "9.9",
            "Volume": "1200",
            "Amount": "12345.6",
        },
    )

    assert snapshot.symbol == "600519.SH"
    assert snapshot.last == 10.2
    assert snapshot.high == 10.3
    assert snapshot.low == 10.0
    assert snapshot.lastClose == 9.9


def test_normalize_snapshot_accepts_lowercase_and_camelcase_fields():
    snapshot = normalize_tdx_snapshot(
        "000001.SZ",
        {
            "now": "9.7",
            "open": "9.5",
            "max": "9.8",
            "min": "9.4",
            "LAST_CLOSE": "9.3",
            "volume": "100",
            "amount": "970",
        },
    )

    assert snapshot.symbol == "000001.SZ"
    assert snapshot.last == 9.7
    assert snapshot.open == 9.5
    assert snapshot.lastClose == 9.3
    assert snapshot.volume == 100.0


def test_http_snapshot_preserves_fill_clock_and_first_alias_policy():
    snapshot = normalize_tdx_snapshot(
        "600519.SH",
        {
            "Now": "10.2",
            "Last": "99.9",
            "Code": "600519.SH",
        },
    )

    assert snapshot.last == 10.2
    assert snapshot.open == 0.0
    assert snapshot.high == 0.0
    assert snapshot.asOf.endswith("+08:00")


def test_http_snapshot_ignores_experimental_only_aliases_and_native_order():
    last_before_now = normalize_tdx_snapshot(
        "600519.SH",
        {
            "Last": "99.9",
            "Now": "10.2",
            "High": "88.8",
            "Low": "1.1",
        },
    )
    aliases_only = normalize_tdx_snapshot(
        "600519.SH",
        {
            "Last": "99.9",
            "Close": "98.8",
            "High": "88.8",
            "Low": "1.1",
        },
    )

    assert last_before_now.last == 10.2
    assert last_before_now.high == 0.0
    assert last_before_now.low == 0.0
    assert aliases_only.last == 0.0
    assert aliases_only.high == 0.0
    assert aliases_only.low == 0.0
