"""TDX realtime native snapshot validator.

Strict validation of native ``get_market_snapshot`` payloads for the
formal builtin-bridge pathway. It applies strict validation after projecting
provider-native fields:

- ``last`` is required and must be a finite number (reject NaN/Inf/bool).
- ``open``/``high``/``low``/``lastClose`` are always present on the typed wire;
  missing native values become ``None`` (never filled with 0).
- ``eventTime`` is ``None`` when the native time is missing (never synthesized
  from the clock).
- Conflicting native aliases (e.g. both ``Now`` and ``Last``) are rejected.

"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.datasource.contracts import normalize_beijing_iso
from src.datasource.tdx.market_normalization import (
    TDX_REALTIME_LOGICAL_ALIAS_GROUPS,
    extract_tdx_snapshot_native_fields,
    normalize_native_key,
    normalize_symbol,
)

#: Fields that the realtime validator treats as optional prices (present
#: but possibly null). ``last`` is required, handled separately.
_OPTIONAL_PRICE_FIELDS = ("open", "high", "low", "lastClose")
_OPTIONAL_NATIVE_FIELDS = ("nativeVolume", "nativeAmount")
_TDX_QUANTITY_PATTERN = re.compile(r"^[0-9]+(?:\.[0-9]{1,8})?$")
_TDX_QUANTITY_MAX_LENGTH = 37
_TDX_QUANTITY_MAX_INTEGER_DIGITS = 28


class TdxRealtimeNativeValidationError(ValueError):
    """Raised when a native snapshot cannot be strictly decoded."""


@dataclass(frozen=True)
class ValidatedTdxNativeSnapshot:
    """Validated TDX native fields used only to accept or reject a frame."""

    symbol: str
    last: float
    open: float | None
    high: float | None
    low: float | None
    lastClose: float | None
    nativeVolume: str | None
    nativeAmount: str | None
    eventTime: str | None
    quality: dict[str, bool]


def _reject_conflicting_aliases(native: Mapping[str, Any]) -> None:
    for logical, aliases in TDX_REALTIME_LOGICAL_ALIAS_GROUPS.items():
        expected = {normalize_native_key(alias) for alias in aliases}
        hits = [
            (key, value)
            for key, value in native.items()
            if normalize_native_key(key) in expected and value is not None and value != ""
        ]
        if len(hits) > 1:
            raise TdxRealtimeNativeValidationError(
                f"conflicting native aliases for field {logical}: {hits}"
            )


def _reject_non_exact_last_close_keys(native: Mapping[str, Any]) -> None:
    for key in native:
        if key == "LastClose":
            continue
        normalized = normalize_native_key(key)
        if normalized in {"lastclose", "preclose"}:
            raise TdxRealtimeNativeValidationError(
                f"TDX realtime previous close must use exact native key LastClose, got {key!r}"
            )


def _reject_non_exact_quantity_keys(native: Mapping[str, Any]) -> None:
    exact_keys = {"Volume", "Amount"}
    for key in native:
        if key in exact_keys:
            continue
        if normalize_native_key(key) in {"volume", "amount"}:
            raise TdxRealtimeNativeValidationError(
                f"TDX realtime quantity must use exact native key Volume/Amount, got {key!r}"
            )


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None and not (isinstance(value, str) and value.strip() == ""):
            return value
    return None


def _finite_float(value: Any, *, field_name: str) -> float:
    """Coerce to float and reject non-finite/bool values."""
    if isinstance(value, bool):
        raise TdxRealtimeNativeValidationError(f"{field_name} is boolean, not a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise TdxRealtimeNativeValidationError(f"{field_name} is not numeric: {value!r}") from exc
    if math.isnan(result) or math.isinf(result):
        raise TdxRealtimeNativeValidationError(f"{field_name} is non-finite: {result}")
    return result


def _optional_finite_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return _finite_float(value, field_name=field_name)


def _optional_quantity_text(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TdxRealtimeNativeValidationError(f"{field_name} must be a native decimal string")
    if len(value) > _TDX_QUANTITY_MAX_LENGTH:
        raise TdxRealtimeNativeValidationError(
            f"{field_name} exceeds {_TDX_QUANTITY_MAX_LENGTH} ASCII characters"
        )
    if _TDX_QUANTITY_PATTERN.fullmatch(value) is None:
        raise TdxRealtimeNativeValidationError(
            f"{field_name} must be unsigned ASCII fixed-point with scale <= 8"
        )
    integer = value.partition(".")[0].lstrip("0") or "0"
    if len(integer) > _TDX_QUANTITY_MAX_INTEGER_DIGITS:
        raise TdxRealtimeNativeValidationError(
            f"{field_name} exceeds {_TDX_QUANTITY_MAX_INTEGER_DIGITS} integer digits"
        )
    return value


def validate_tdx_realtime_native_snapshot(
    symbol: str,
    native: Mapping[str, Any],
    *,
    expected_code: str | None = None,
) -> ValidatedTdxNativeSnapshot:
    """Strictly validate a native snapshot without changing its wire shape.

    Raises ``TdxRealtimeNativeValidationError`` when ``last`` is missing/non-finite,
    when ``ErrorId`` indicates a provider error, or when conflicting aliases
    are present.
    """
    _reject_non_exact_last_close_keys(native)
    _reject_non_exact_quantity_keys(native)
    _reject_conflicting_aliases(native)
    raw = extract_tdx_snapshot_native_fields(native)

    # Provider error check.
    error_id = raw.error_id
    if error_id is not None and str(error_id) != "0" and str(error_id) != "":
        raise TdxRealtimeNativeValidationError(f"native ErrorId={error_id!r} for {symbol}")

    # The official get_market_snapshot response does not include Code. The
    # bridge binds the response to the requested symbol in its snapshot
    # envelope. Some TDX builds do include Code; validate it when present.
    if raw.code is not None and not (isinstance(raw.code, str) and raw.code.strip() == ""):
        expected = normalize_symbol(expected_code or symbol)
        actual = normalize_symbol(str(raw.code))
        if actual != expected:
            raise TdxRealtimeNativeValidationError(
                f"native Code {raw.code!r} != expected {expected_code or symbol!r}"
            )

    # Logical aliases are resolved only after the conflict check. The HTTP
    # projector never consumes these realtime alternatives.
    raw_last = _first_present(raw.now, raw.last, raw.close)
    raw_high = _first_present(raw.maximum, raw.high)
    raw_low = _first_present(raw.minimum, raw.low)

    # last is required + finite.
    if raw_last is None:
        raise TdxRealtimeNativeValidationError(f"last is missing for {symbol}")
    last = _finite_float(raw_last, field_name="last")

    # Optional prices: present-or-null.
    open_ = _optional_finite_float(raw.open, field_name="open")
    high = _optional_finite_float(raw_high, field_name="high")
    low = _optional_finite_float(raw_low, field_name="low")
    last_close = _optional_finite_float(raw.lastClose, field_name="lastClose")
    native_volume = _optional_quantity_text(raw.nativeVolume, field_name="Volume")
    native_amount = _optional_quantity_text(raw.nativeAmount, field_name="Amount")

    # eventTime: null if missing (NEVER clock-filled).
    event_time: str | None = None
    native_time_unavailable = True
    if raw.eventTime is not None and not (
        isinstance(raw.eventTime, str) and raw.eventTime.strip() == ""
    ):
        parsed = normalize_beijing_iso(raw.eventTime)
        if parsed is not None:
            event_time = parsed
            native_time_unavailable = False

    quality: dict[str, bool] = {}
    partial = any(v is None for v in (open_, high, low, last_close))
    if partial:
        quality["partialPrices"] = True
    if native_time_unavailable:
        quality["nativeTimeUnavailable"] = True

    return ValidatedTdxNativeSnapshot(
        symbol=symbol,
        last=last,
        open=open_,
        high=high,
        low=low,
        lastClose=last_close,
        nativeVolume=native_volume,
        nativeAmount=native_amount,
        eventTime=event_time,
        quality=quality,
    )
