import json
import re
from typing import Any, cast

MAX_NATIVE_JSON_BYTES = 64 * 1024
MAX_NATIVE_DEPTH = 8
SENSITIVE_KEY = re.compile(r"(?:password|passwd|token|secret|credential|account)", re.I)


class NativePayloadSafetyError(ValueError):
    pass


def validate_native_payload_safety(value: dict[str, Any]) -> None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_NATIVE_JSON_BYTES:
        raise NativePayloadSafetyError("native payload exceeds 64 KiB")
    _walk(value, depth=1)


def _walk(value: Any, *, depth: int) -> None:
    if depth > MAX_NATIVE_DEPTH:
        raise NativePayloadSafetyError("native payload exceeds maximum depth")
    if isinstance(value, dict):
        for key, item in cast(dict[Any, Any], value).items():
            if SENSITIVE_KEY.search(str(key)):
                raise NativePayloadSafetyError("native payload contains a sensitive field")
            _walk(item, depth=depth + 1)
    elif isinstance(value, list):
        for item in cast(list[Any], value):
            _walk(item, depth=depth + 1)
