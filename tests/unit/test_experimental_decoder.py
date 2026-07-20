"""Unit tests for the experimental TDX realtime decoder (strict validation)."""

from __future__ import annotations

import json
from pathlib import Path

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

    def test_experimental_only_aliases_are_resolved(self) -> None:
        native = _native(Last="1685.0", High="1690.0", Low="1665.0")
        del native["Now"]
        del native["Max"]
        del native["Min"]

        snap = decode_experimental_tdx_snapshot("600519.SH", native)

        assert snap.last == 1685.0
        assert snap.high == 1690.0
        assert snap.low == 1665.0

    def test_official_snapshot_without_code_uses_envelope_symbol(self) -> None:
        snap = decode_experimental_tdx_snapshot(
            "600519.SH",
            _native(),
            expected_code="600519.SH",
        )

        assert snap.symbol == "600519.SH"

    def test_optional_native_code_accepts_prefix_format(self) -> None:
        snap = decode_experimental_tdx_snapshot(
            "600519.SH",
            _native(Code="SH600519"),
            expected_code="600519.SH",
        )

        assert snap.symbol == "600519.SH"


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

    def test_same_value_aliases_are_still_rejected(self) -> None:
        native = _native(Now="1685.0", Last="1685.0")
        with pytest.raises(ExperimentalDecoderError, match="conflicting"):
            decode_experimental_tdx_snapshot("600519.SH", native)


def test_f0_fixture_cases_and_existing_mock_snapshot() -> None:
    fixture_root = Path(__file__).resolve().parents[1] / "fixtures" / "tdx"
    f0 = json.loads((fixture_root / "experimental_f0_cases.json").read_text())
    assert f0["evidenceTier"] == "F0-hand-crafted"
    normal = f0["normal"]
    assert decode_experimental_tdx_snapshot("600519.SH", normal).last == 1685.0
    for case in f0["abnormal"]:
        native = {**normal, **case["overrides"]}
        with pytest.raises(ExperimentalDecoderError, match=case["errorMatch"]):
            decode_experimental_tdx_snapshot("600519.SH", native, expected_code="600519.SH")

    mock_snapshot = json.loads((fixture_root / "snapshot.json").read_text())
    decoded_mock = decode_experimental_tdx_snapshot("mock.SH", {**mock_snapshot, "Code": "mock.SH"})
    assert decoded_mock.last == 35.06


def test_f1_fixture_is_explicitly_external_and_runtime_unknown() -> None:
    fixture = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "fixtures"
            / "tdx"
            / "live_market_snapshot_600519.json"
        ).read_text()
    )
    assert fixture["evidenceTier"] == "F1-external-http"
    assert fixture["runtimeVersion"] == "unknown"
