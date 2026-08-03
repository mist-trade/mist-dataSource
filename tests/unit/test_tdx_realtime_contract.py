"""Exact native-key tests for the TDX realtime snapshot contract."""

import pytest

from src.datasource.tdx.realtime.contract import (
    TdxRealtimeNativeValidationError,
    validate_tdx_realtime_native_snapshot,
)


def test_accepts_exact_native_last_close() -> None:
    snapshot = validate_tdx_realtime_native_snapshot(
        "600519.SH",
        {"Now": "1685.0", "LastClose": "1672.5"},
    )

    assert snapshot.lastClose == 1672.5


def test_preserves_valid_quantity_strings_without_normalizing_wire_values() -> None:
    snapshot = validate_tdx_realtime_native_snapshot(
        "600519.SH",
        {
            "Now": "1685.0",
            "Volume": "000576508.00000000",
            "Amount": "163965.55000000",
        },
    )

    assert snapshot.nativeVolume == "000576508.00000000"
    assert snapshot.nativeAmount == "163965.55000000"


def test_keeps_absent_and_explicit_null_quantities_distinct_from_zero() -> None:
    absent = validate_tdx_realtime_native_snapshot("600519.SH", {"Now": "1685.0"})
    explicit_null = validate_tdx_realtime_native_snapshot(
        "600519.SH", {"Now": "1685.0", "Volume": None, "Amount": None}
    )
    zero = validate_tdx_realtime_native_snapshot(
        "600519.SH", {"Now": "1685.0", "Volume": "0", "Amount": "0.00000000"}
    )

    assert absent.nativeVolume is None
    assert absent.nativeAmount is None
    assert explicit_null.nativeVolume is None
    assert explicit_null.nativeAmount is None
    assert zero.nativeVolume == "0"
    assert zero.nativeAmount == "0.00000000"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Volume", 1),
        ("Amount", 1.5),
        ("Volume", ""),
        ("Amount", " 1"),
        ("Volume", "+1"),
        ("Amount", "-0"),
        ("Volume", "1e2"),
        ("Amount", ".5"),
        ("Volume", "1."),
        ("Amount", "1.230000000"),
        ("Volume", "0" * 38),
        ("Amount", "10000000000000000000000000000"),
    ],
)
def test_rejects_malformed_present_quantity(field: str, value: object) -> None:
    with pytest.raises(TdxRealtimeNativeValidationError):
        validate_tdx_realtime_native_snapshot("600519.SH", {"Now": "1685.0", field: value})


@pytest.mark.parametrize("field", ["volume", "VOLUME", "amount", "AMOUNT"])
def test_rejects_non_exact_quantity_key(field: str) -> None:
    with pytest.raises(
        TdxRealtimeNativeValidationError,
        match="must use exact native key Volume/Amount",
    ):
        validate_tdx_realtime_native_snapshot("600519.SH", {"Now": "1685.0", field: "1"})


@pytest.mark.parametrize(
    "retired_key",
    ["PreClose", "lastClose", "LAST_CLOSE", "last close", "PRE_CLOSE"],
)
def test_rejects_non_exact_previous_close_keys(retired_key: str) -> None:
    with pytest.raises(
        TdxRealtimeNativeValidationError,
        match="must use exact native key LastClose",
    ):
        validate_tdx_realtime_native_snapshot(
            "600519.SH",
            {"Now": "1685.0", retired_key: "1672.5"},
        )
