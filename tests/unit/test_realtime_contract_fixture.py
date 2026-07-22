import hashlib
import json
from pathlib import Path

CONTRACT = Path(__file__).resolve().parents[2] / "contracts/realtime/realtime-native-frame-v1.json"
MANIFEST = CONTRACT.with_name("manifest.json")


def test_realtime_contract_fixture_sha_and_shape() -> None:
    raw = CONTRACT.read_bytes()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fixture = json.loads(raw)

    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    assert fixture["contract"] == {
        "payloadType": "mist.realtime.native_snapshot",
        "schemaVersion": 1,
        "sequenceScope": "symbol",
    }
    assert fixture["cases"]["tdxSnapshot"]["data"]["native"]["Now"] == 31.25
    assert fixture["cases"]["qmtSnapshot"]["data"]["native"]["lastPrice"] == 541.2
    assert fixture["cases"]["qmtInterleavedSecondSymbol"]["data"]["sequence"] == 1
