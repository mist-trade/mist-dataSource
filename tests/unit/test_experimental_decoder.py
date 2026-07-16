"""Unit tests for the experimental TDX realtime decoder (strict validation)."""

from __future__ import annotations

import pytest

from src.datasource.tdx.experimental_decoder import (
    ExperimentalDecoderError,
    decode_experimental_tdx_snapshot,
)


def _native(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "Now": "1685.0",
        "Open": "1670.0",
        "Max": "1690.0",
        "Min": "1665.0",
        "LastClose": "1672.5",
        "Volume": "12345600",
        "Amount": "20800000000",
        "AsOf": "2026-07-16T14:30:00.000+08:00",
        "Code": "600519.SH",
        "ErrorId": "0",
    }
    base.update(overrides)
    return base


class TestDecodeValid:
    def test_full_snapshot(self) -> None:
        snap = decode_experimental_tdx_snapshot("600519.SH", _native())
        assert snap.last == 1685.0
        assert snap.open == 1670.0
        assert snap.high == 1690.0
        assert snap.low == 1665.0
        assert snap.lastClose == 1672.5
        assert snap.nativeVolume == 12345600.0
        assert snap.nativeAmount == 20800000000.0
        assert snap.eventTime is not None
        assert snap.quality == {}

    def test_partial_prices_missing_high_low(self) -> None:
        native = _native()
        del native["Max"]
        del native["Min"]
        snap = decode_experimental_tdx_snapshot("600519.SH", native)
        assert snap.high is None
        assert snap.low is None
        assert snap.last == 1685.0
        assert snap.quality.get("partialPrices") is True

    def test_missing_event_time_becomes_null(self) -> None:
        native = _native()
        del native["AsOf"]
        snap = decode_experimental_tdx_snapshot("600519.SH", native)
        assert snap.eventTime is None
        assert snap.quality.get("nativeTimeUnavailable") is True


class TestDecodeReject:
    def test_missing_last_rejected(self) -> None:
        native = _native()
        del native["Now"]
        with pytest.raises(ExperimentalDecoderError, match="last is missing"):
            decode_experimental_tdx_snapshot("600519.SH", native)

    def test_nan_last_rejected(self) -> None:
        native = _native(Now=float("nan"))
        with pytest.raises(ExperimentalDecoderError, match="non-finite"):
            decode_experimental_tdx_snapshot("600519.SH", native)

    def test_infinity_last_rejected(self) -> None:
        native = _native(Now=float("inf"))
        with pytest.raises(ExperimentalDecoderError, match="non-finite"):
            decode_experimental_tdx_snapshot("600519.SH", native)

    def test_boolean_last_rejected(self) -> None:
        native = _native(Now=True)
        with pytest.raises(ExperimentalDecoderError, match="boolean"):
            decode_experimental_tdx_snapshot("600519.SH", native)

    def test_error_id_nonzero_rejected(self) -> None:
        native = _native(ErrorId="99")
        with pytest.raises(ExperimentalDecoderError, match="ErrorId"):
            decode_experimental_tdx_snapshot("600519.SH", native)

    def test_symbol_mismatch_rejected(self) -> None:
        native = _native(Code="999999.SZ")
        with pytest.raises(ExperimentalDecoderError, match="Code"):
            decode_experimental_tdx_snapshot("600519.SH", native, expected_code="600519.SH")

    def test_conflicting_aliases_rejected(self) -> None:
        native = _native(Now="1685.0", Last="9999.0")
        with pytest.raises(ExperimentalDecoderError, match="conflicting"):
            decode_experimental_tdx_snapshot("600519.SH", native)
