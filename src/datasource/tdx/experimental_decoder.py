"""Experimental TDX realtime decoder.

Strict validation of native ``get_market_snapshot`` payloads for the
experimental builtin-bridge pathway. Shares the raw field-projection table
with the HTTP path but applies its own validation policy:

- ``last`` is required and must be a finite number (reject NaN/Inf/bool).
- ``open``/``high``/``low``/``lastClose`` are always present on the typed wire;
  missing native values become ``None`` (never filled with 0).
- ``eventTime`` is ``None`` when the native time is missing (never synthesized
  from the clock).
- Conflicting native aliases (e.g. both ``Now`` and ``Last``) are rejected.

This module deliberately does NOT reuse ``normalize_tdx_snapshot`` (which fills
missing prices with 0) or ``normalize_number`` (which maps ``None`` -> ``0.0``).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from src.datasource.contracts import normalize_beijing_iso
from src.datasource.tdx_normalization import native_value

# Shared field-name alias table (native -> logical). Both the HTTP projector
# (via normalize_tdx_snapshot) and this experimental decoder resolve native
# keys through this mapping, but each applies its own fill/validation policy.
TDX_SNAPSHOT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "last": ("Now", "now", "Last", "last", "Close", "close"),
    "open": ("Open", "open"),
    "high": ("Max", "max", "High", "high"),
    "low": ("Min", "min", "Low", "low"),
    "lastClose": ("LastClose", "lastClose", "lastclose"),
    "nativeVolume": ("Volume", "volume"),
    "nativeAmount": ("Amount", "amount"),
    "eventTime": ("AsOf", "asOf", "asof"),
}

#: Fields that the experimental typed wire treats as optional prices (present
#: but possibly null). ``last`` is required, handled separately.
_OPTIONAL_PRICE_FIELDS = ("open", "high", "low", "lastClose")
_OPTIONAL_NATIVE_FIELDS = ("nativeVolume", "nativeAmount")


class ExperimentalDecoderError(ValueError):
    """Raised when a native snapshot cannot be strictly decoded."""


@dataclass(frozen=True)
class RawTdxSnapshotFields:
    """Raw optional values extracted from native, before any fill or model."""

    last: Any = None
    open: Any = None
    high: Any = None
    low: Any = None
    lastClose: Any = None
    nativeVolume: Any = None
    nativeAmount: Any = None
    eventTime: Any = None
    error_id: Any = None
    code: Any = None
    # Track which aliases actually resolved, for conflict detection.
    resolved_aliases: dict[str, str] = field(default_factory=lambda: dict[str, str]())


@dataclass(frozen=True)
class ExperimentalTdxSnapshot:
    """Strictly validated typed snapshot emitted on the experimental wire."""

    symbol: str
    last: float
    open: float | None
    high: float | None
    low: float | None
    lastClose: float | None
    nativeVolume: float | None
    nativeAmount: float | None
    eventTime: str | None
    quality: dict[str, bool]


def extract_tdx_snapshot_native_fields(
    native: Mapping[str, Any],
) -> RawTdxSnapshotFields:
    """Extract raw optional values from native without filling or modelling.

    Shared with the HTTP path: returns native values resolved through the alias
    table. No conversion, no defaults — callers apply their own policy.
    """
    resolved: dict[str, str] = {}
    values: dict[str, Any] = {}
    for logical, aliases in TDX_SNAPSHOT_FIELD_ALIASES.items():
        value, hit_key = _resolve_alias_strict(native, aliases)
        values[logical] = value
        if hit_key is not None:
            resolved[logical] = hit_key
    return RawTdxSnapshotFields(
        last=values["last"],
        open=values["open"],
        high=values["high"],
        low=values["low"],
        lastClose=values["lastClose"],
        nativeVolume=values["nativeVolume"],
        nativeAmount=values["nativeAmount"],
        eventTime=values["eventTime"],
        error_id=native_value(native, "ErrorId", "errorid", "error_id"),
        code=native_value(native, "Code", "code"),
        resolved_aliases=resolved,
    )


def _resolve_alias_strict(
    native: Mapping[str, Any], aliases: tuple[str, ...]
) -> tuple[Any, str | None]:
    """Resolve a logical field, rejecting conflicting aliases.

    Returns ``(value, hit_key)``. If multiple distinct normalized aliases map
    to non-None values that differ, raise (strict — do not rely on dict order).
    """
    # Reuse native_value's key normalization for consistency.
    from src.datasource.tdx_normalization import normalize_native_key

    expected = {normalize_native_key(a) for a in aliases}
    hits: list[tuple[str, Any]] = []
    for key, value in native.items():
        if normalize_native_key(key) in expected and value is not None and value != "":
            hits.append((key, value))
    if not hits:
        return None, None
    # Check for conflicts among the resolved non-None values.
    distinct_values: set[Any] = set()
    for _, v in hits:
        distinct_values.add(v)
    if len(distinct_values) > 1:
        raise ExperimentalDecoderError(f"conflicting native aliases for field {aliases[0]}: {hits}")
    return hits[0][1], hits[0][0]


def _finite_float(value: Any, *, field_name: str) -> float:
    """Coerce to float and reject non-finite/bool values."""
    if isinstance(value, bool):
        raise ExperimentalDecoderError(f"{field_name} is boolean, not a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ExperimentalDecoderError(f"{field_name} is not numeric: {value!r}") from exc
    if math.isnan(result) or math.isinf(result):
        raise ExperimentalDecoderError(f"{field_name} is non-finite: {result}")
    return result


def _optional_finite_float(value: Any, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return _finite_float(value, field_name=field_name)


def decode_experimental_tdx_snapshot(
    symbol: str,
    native: Mapping[str, Any],
    *,
    expected_code: str | None = None,
) -> ExperimentalTdxSnapshot:
    """Strictly decode a native snapshot into the experimental typed wire.

    Raises ``ExperimentalDecoderError`` when ``last`` is missing/non-finite,
    when ``ErrorId`` indicates a provider error, or when conflicting aliases
    are present.
    """
    raw = extract_tdx_snapshot_native_fields(native)

    # Provider error check.
    error_id = raw.error_id
    if error_id is not None and str(error_id) != "0" and str(error_id) != "":
        raise ExperimentalDecoderError(f"native ErrorId={error_id!r} for {symbol}")

    # Code is required (must be present in native payload).
    if raw.code is None or (isinstance(raw.code, str) and raw.code.strip() == ""):
        raise ExperimentalDecoderError(f"native Code is missing for {symbol}")

    # Symbol consistency if provided.
    if expected_code is not None and str(raw.code) != str(expected_code):
        raise ExperimentalDecoderError(f"native Code {raw.code!r} != expected {expected_code!r}")

    # last is required + finite.
    if raw.last is None or (isinstance(raw.last, str) and raw.last.strip() == ""):
        raise ExperimentalDecoderError(f"last is missing for {symbol}")
    last = _finite_float(raw.last, field_name="last")

    # Optional prices: present-or-null.
    open_ = _optional_finite_float(raw.open, field_name="open")
    high = _optional_finite_float(raw.high, field_name="high")
    low = _optional_finite_float(raw.low, field_name="low")
    last_close = _optional_finite_float(raw.lastClose, field_name="lastClose")
    native_volume = _optional_finite_float(raw.nativeVolume, field_name="nativeVolume")
    native_amount = _optional_finite_float(raw.nativeAmount, field_name="nativeAmount")

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

    return ExperimentalTdxSnapshot(
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
