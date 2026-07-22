import hashlib
import json
from pathlib import Path

CONTRACT = (
    Path(__file__).resolve().parents[1]
    / "fixtures/realtime/realtime-native-frame-v1.json"
)
CHECKSUM = CONTRACT.with_suffix(".sha256")


def test_realtime_contract_fixture_sha_and_shape() -> None:
    raw = CONTRACT.read_bytes()
    expected_sha = CHECKSUM.read_text(encoding="utf-8").split()[0]
    fixture = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == expected_sha
    assert fixture["contract"] == {
        "payloadType": "mist.realtime.native_snapshot",
        "schemaVersion": 1,
        "sequenceScope": "symbol",
    }
    assert fixture["cases"]["tdxSnapshot"]["data"]["native"]["Now"] == 31.25
    assert fixture["cases"]["qmtSnapshot"]["data"]["native"]["lastPrice"] == 541.2
    assert fixture["cases"]["qmtInterleavedSecondSymbol"]["data"]["sequence"] == 1
