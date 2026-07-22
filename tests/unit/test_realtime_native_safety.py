import pytest

from src.datasource.realtime_native_safety import (
    NativePayloadSafetyError,
    validate_native_payload_safety,
)


def test_native_payload_safety_accepts_bounded_provider_fields() -> None:
    validate_native_payload_safety({"Now": 31.25, "bid": [[31.2, 100]]})


@pytest.mark.parametrize(
    "native",
    [
        {"authToken": "must-not-cross-wire"},
        {"nested": {"password": "must-not-cross-wire"}},
        {"nested": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": 1}}}}}}}}},
        {"payload": "x" * (64 * 1024)},
    ],
)
def test_native_payload_safety_rejects_sensitive_oversized_or_deep_values(native) -> None:
    with pytest.raises(NativePayloadSafetyError):
        validate_native_payload_safety(native)
