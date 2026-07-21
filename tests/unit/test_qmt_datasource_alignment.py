from pathlib import Path

from src.datasource.capabilities import build_provider_manifests
from src.datasource.contracts import ResponseEnvelope

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tdx_provider_manifest_no_longer_lists_qmt() -> None:
    manifests = build_provider_manifests(tdx_status="available")

    assert [manifest.id for manifest in manifests] == ["tdx"]


def test_qmt_alignment_reference_records_native_service_path() -> None:
    reference = PROJECT_ROOT / "docs" / "references" / "qmt-provider-alignment.md"
    text = reference.read_text(encoding="utf-8")

    assert "`:9002/v1/bars/query`" in text
    assert "QMT native `marketData`" in text
    assert "`get_market_data_ex(..., subscribe=False)`" in text
    assert "no shared TDX adapter layer exists" in text
    assert "`/api/qmt/*`" not in text
    assert "`provider=qmt`" not in text
    assert "WebSocket duplex" not in text


def test_qmt_has_no_legacy_adapter_package_source() -> None:
    adapter_qmt = PROJECT_ROOT / "src" / "adapter" / "qmt"

    assert not [path for path in adapter_qmt.glob("*.py") if path.name != "__init__.py"]
    assert not (adapter_qmt / "__init__.py").exists()


def test_qmt_native_market_data_envelope_keeps_column_shape() -> None:
    envelope = ResponseEnvelope.success(
        request_id="req-qmt-native",
        provider="qmt",
        data={
            "marketData": {
                "000001.SZ": {
                    "open": {"20260701": 10.05},
                    "close": {"20260701": 10.16},
                    "volume": {"20260701": 906890.0},
                    "amount": {"20260701": 915838549.0},
                }
            },
            "source": "native_bridge",
        },
    )

    payload = envelope.model_dump()

    assert payload["provider"] == "qmt"
    assert "bars" not in payload["data"]
    assert payload["data"]["marketData"]["000001.SZ"]["close"] == {"20260701": 10.16}
