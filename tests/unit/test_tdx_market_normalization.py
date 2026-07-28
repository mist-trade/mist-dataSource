"""Tests for TDX market normalization boundaries."""

from decimal import Decimal

import pandas as pd
import pytest

from src.datasource.tdx.market_normalization import (
    TdxBarNormalizationError,
    native_value,
    normalize_native_key,
    normalize_optional_number,
    normalize_symbol,
    normalize_tdx_bar_rows,
    to_tdx_code,
    to_tdx_http_code,
)
from src.datasource.tdx.models import TdxBar, TdxBarQueryRequest


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


@pytest.mark.parametrize(
    ("native_value", "expected"),
    [
        ("0", Decimal("0")),
        ("5086297.00", Decimal("5086297")),
        ("12345.67890123", Decimal("12345.67890123")),
        (None, None),
        ("", None),
        ("not-a-number", None),
        ("NaN", None),
        ("Infinity", None),
        ("-Infinity", None),
    ],
)
def test_historical_measure_normalization_preserves_exact_values_or_null(native_value, expected):
    from src.datasource.contracts import normalize_nullable_k_decimal

    assert normalize_nullable_k_decimal(native_value) == expected


@pytest.mark.parametrize(
    "native_value",
    ["12345678901234567890123456789", "0.123456789"],
)
def test_historical_measure_normalization_rejects_out_of_range_values(native_value):
    from src.datasource.contracts import normalize_nullable_k_decimal

    with pytest.raises(ValueError, match="exceeds"):
        normalize_nullable_k_decimal(native_value)


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


def test_tdx_bar_serializes_exact_decimal_measures_and_explicit_nulls():
    bar = TdxBar(
        symbol="600519.SH",
        period="1m",
        barTime="2026-06-26T09:31:00",
        open=10.1,
        high=10.3,
        low=10.0,
        close=10.2,
        volume=Decimal("1234.56789012"),
        amount=None,
        provider="tdx",
        receivedAt="2026-06-26T09:31:02",
    )

    assert '"volume":"1234.56789012"' in bar.model_dump_json()
    assert '"amount":null' in bar.model_dump_json()


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


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("Close", None, "missing"),
        ("High", "", "blank"),
        ("Low", "not-a-number", "not_numeric"),
        ("Open", "Infinity", "not_finite"),
    ],
)
def test_normalize_bar_rows_rejects_invalid_required_prices(
    field: str, value: object, reason: str
) -> None:
    timestamp = "2026-06-26T09:31:00"
    native = {
        "Open": {"SH600519": {timestamp: "10.1"}},
        "High": {"SH600519": {timestamp: "10.3"}},
        "Low": {"SH600519": {timestamp: "10.0"}},
        "Close": {"SH600519": {timestamp: "10.2"}},
        "Volume": {"SH600519": {timestamp: "1200"}},
        "Amount": {"SH600519": {timestamp: "12345.6"}},
    }
    if value is None:
        native[field]["SH600519"].pop(timestamp)
    else:
        native[field]["SH600519"][timestamp] = value

    with pytest.raises(TdxBarNormalizationError) as captured:
        normalize_tdx_bar_rows("SH600519", "1m", native)

    assert captured.value.code == "TDX_BAR_REQUIRED_PRICE_INVALID"
    assert captured.value.retryable is False
    assert captured.value.details == {
        "source": "tdx",
        "symbol": "600519.SH",
        "timestamp": timestamp,
        "invalidFields": {field.lower(): reason},
    }


def test_normalize_bar_rows_preserves_explicit_zero_required_price() -> None:
    timestamp = "2026-06-26T09:31:00"
    rows = normalize_tdx_bar_rows(
        symbol="SH600519",
        period="1m",
        native={
            "Open": {"SH600519": {timestamp: 0}},
            "High": {"SH600519": {timestamp: 0}},
            "Low": {"SH600519": {timestamp: 0}},
            "Close": {"SH600519": {timestamp: 0}},
        },
    )

    assert len(rows) == 1
    assert (rows[0].open, rows[0].high, rows[0].low, rows[0].close) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )


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
    assert rows[1].amount == Decimal("592201.44")


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
