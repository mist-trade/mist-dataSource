from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.adapter.mock.qmt_mock import QMTMockAdapter
from src.datasource.capabilities import (
    QMT_CAPABILITY_STATUSES,
    build_provider_manifests,
)
from src.datasource.contracts import ResponseEnvelope
from src.datasource.tdx_models import TdxBar, TdxSnapshot

FIRST_QMT_PARITY_TARGETS = {
    "bars": {"get_market_data_ex"},
    "snapshots": {"get_full_tick"},
    "calendar": {"trading_calendar"},
    "securities": {"get_stock_list_in_sector"},
    "security-info": {"instrument_detail"},
    "sector-list": {"sector_list"},
    "sector-members": {"get_stock_list_in_sector"},
}


def test_qmt_manifest_records_first_parity_target_set() -> None:
    qmt_manifest = next(
        manifest
        for manifest in build_provider_manifests(tdx_status="available")
        if manifest.id == "qmt"
    )
    qmt_capabilities = {
        capability.family: capability.model_dump() for capability in qmt_manifest.capabilities
    }

    for family, expected_methods in FIRST_QMT_PARITY_TARGETS.items():
        capability = qmt_capabilities[family]
        assert capability["status"] == "unsupported"
        assert capability["stability"] == "spike-blocked"
        assert capability["unsupportedReason"] == "Full-QMT bridge Windows spike evidence is required"
        assert expected_methods <= set(capability["nativeMethods"])
        assert capability["providerMethods"]

    assert "get_bars" in qmt_capabilities["bars"]["providerMethods"]
    assert "get_market_data" not in qmt_capabilities["bars"]["providerMethods"]


def test_qmt_manifest_keeps_unverified_capabilities_explicit() -> None:
    unsupported_families = {
        "reference-data",
        "finance-report",
        "financial-data",
        "formula-data",
        "formula-execution",
        "formula-batch-execution",
        "formulas",
        "raw-diagnostics",
    }

    for family in unsupported_families:
        status, _stability, methods, unsupported_reason = QMT_CAPABILITY_STATUSES[family]
        assert status == "unsupported"
        assert methods == []
        assert unsupported_reason

    assert "report-data" not in QMT_CAPABILITY_STATUSES


@pytest.mark.asyncio
async def test_qmt_mock_adapter_covers_first_parity_native_methods() -> None:
    adapter = QMTMockAdapter(path="/mock/qmt", account_id="mock")
    await adapter.initialize()

    try:
        market_data = await adapter.get_market_data(["600000.SH"], ["close"], count=1)
        ticks = await adapter.get_full_tick(["600000.SH"])
        trading_dates = await adapter.get_trading_dates("SH", count=2)
        securities = await adapter.get_stock_list("0")
        members = await adapter.get_stock_list_in_sector("沪深300")
        sectors = await adapter.get_sector_list()
        detail = await adapter.get_instrument_detail("600000.SH")
        instrument_type = await adapter.get_instrument_type("600000.SH")
    finally:
        await adapter.shutdown()

    assert "close" in market_data
    assert "600000.SH" in ticks
    assert trading_dates
    assert securities
    assert members
    assert sectors
    assert detail["InstrumentID"] == "600000.SH"
    assert instrument_type["stock"] is True


@pytest.mark.asyncio
async def test_qmt_mock_adapter_covers_later_reference_and_finance_candidates() -> None:
    adapter = QMTMockAdapter(path="/mock/qmt", account_id="mock")
    await adapter.initialize()

    try:
        dividend_factors = await adapter.get_divid_factors("600000.SH")
        cb_info = await adapter.get_cb_info("113001.SH")
        ipo_info = await adapter.get_ipo_info()
        etf_info = await adapter.get_etf_info()
        financial_data = await adapter.get_financial_data(["600000.SH"], ["Balance"])
    finally:
        await adapter.shutdown()

    assert dividend_factors
    assert cb_info["stock_code"] == "113001.SH"
    assert ipo_info == []
    assert etf_info == {}
    assert financial_data == {"600000.SH": {}}


def test_qmt_alignment_reference_records_current_path_and_first_targets() -> None:
    reference = Path("docs/references/qmt-provider-alignment.md")
    text = reference.read_text(encoding="utf-8")

    assert "First Parity Target Set" in text
    for family in FIRST_QMT_PARITY_TARGETS:
        assert f"`{family}`" in text
    assert "`/api/qmt/*`" in text
    assert "`/v1`" in text
    assert "QMT live startup remains disabled" in text
    assert "full-QMT built-in Python script polls the gateway" in text


def test_provider_neutral_public_models_do_not_use_tdx_native_field_names() -> None:
    bar = TdxBar(
        symbol="600000.SH",
        period="1m",
        barTime="2026-06-27T09:31:00+08:00",
        open=10.0,
        high=10.2,
        low=9.9,
        close=10.1,
        volume=1000.0,
        amount=10100.0,
        receivedAt=datetime(2026, 6, 27, 9, 31, tzinfo=UTC),
    )
    snapshot = TdxSnapshot(
        symbol="600000.SH",
        last=10.1,
        open=10.0,
        high=10.2,
        low=9.9,
        lastClose=9.8,
        volume=1000.0,
        amount=10100.0,
        asOf="2026-06-27T09:31:00+08:00",
    )
    envelope = ResponseEnvelope.success(
        request_id="req-qmt-neutral",
        provider="qmt",
        data={
            "bars": [bar.model_dump()],
            "snapshots": [snapshot.model_dump()],
        },
    )

    serialized = envelope.model_dump()
    forbidden_keys = {
        "Amount",
        "Close",
        "ErrorId",
        "High",
        "LastClose",
        "Low",
        "Max",
        "Min",
        "Now",
        "Open",
        "Value",
        "field_list",
        "stock_code",
    }
    discovered_keys = set(_walk_public_keys(serialized))

    assert forbidden_keys.isdisjoint(discovered_keys)


def _walk_public_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        keys = list(value)
        for child_value in value.values():
            keys.extend(_walk_public_keys(child_value))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for item in value:
            keys.extend(_walk_public_keys(item))
        return keys
    return []
