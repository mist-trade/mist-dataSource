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
