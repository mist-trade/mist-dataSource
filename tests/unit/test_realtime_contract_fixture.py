import hashlib
import json
from pathlib import Path

CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/realtime/realtime-native-frame-v2.json"
)
CHECKSUM = CONTRACT.with_suffix(".sha256")


def test_realtime_contract_fixture_sha_and_shape() -> None:
    raw = CONTRACT.read_bytes()
    expected_sha = CHECKSUM.read_text(encoding="utf-8").split()[0]
    fixture = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == expected_sha
    assert fixture["contract"] == {
        "schemaVersion": 2,
        "outerKeys": ["type", "provider", "timestamp", "data"],
        "dataKeys": ["schemaVersion", "capturedAt", "native"],
    }
    assert (
        fixture["cases"]["tdxOneEntry"]["data"]["native"]["600030.SH"]["Now"]
        == 31.25
    )
    assert (
        fixture["cases"]["qmtOneEntry"]["data"]["native"]["300502.SZ"]["lastPrice"]
        == 541.2
    )
    tdx_native = fixture["cases"]["tdxOneEntry"]["data"]["native"]["600030.SH"]
    qmt_native = fixture["cases"]["qmtOneEntry"]["data"]["native"]["300502.SZ"]
    assert isinstance(tdx_native["Volume"], str)
    assert isinstance(tdx_native["Amount"], str)
    assert isinstance(qmt_native["volume"], int) and not isinstance(
        qmt_native["volume"], bool
    )
    assert isinstance(qmt_native["amount"], int | float) and not isinstance(
        qmt_native["amount"], bool
    )
    assert len(fixture["cases"]["qmtMultiEntry"]["data"]["native"]) == 2
