"""Normalize TDX market bars, snapshots, and provider-native fields."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from src.datasource.contracts import BEIJING_TZ, normalize_beijing_iso
from src.datasource.tdx.models import TdxBar, TdxSnapshot

TDX_SNAPSHOT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    # Keep provider fields separate. In particular, Now/Last/Close and
    # Max/High/Min/Low must not be merged before the consumer chooses its
    # policy: the formal HTTP projector historically reads only Now/Max/Min.
    "now": ("Now",),
    "last": ("Last",),
    "close": ("Close",),
    "open": ("Open",),
    "maximum": ("Max",),
    "high": ("High",),
    "minimum": ("Min",),
    "low": ("Low",),
    "lastClose": ("LastClose",),
    "nativeVolume": ("Volume",),
    "nativeAmount": ("Amount",),
    "eventTime": ("AsOf",),
}

TDX_REALTIME_LOGICAL_ALIAS_GROUPS: dict[str, tuple[str, ...]] = {
    "last": ("Now", "Last", "Close"),
    "open": ("Open",),
    "high": ("Max", "High"),
    "low": ("Min", "Low"),
    "lastClose": ("LastClose",),
    "nativeVolume": ("Volume",),
    "nativeAmount": ("Amount",),
    "eventTime": ("AsOf",),
}


@dataclass(frozen=True)
class RawTdxSnapshotFields:
    """Native snapshot values before conversion, filling, or modelling."""

    now: Any = None
    last: Any = None
    close: Any = None
    open: Any = None
    maximum: Any = None
    high: Any = None
    minimum: Any = None
    low: Any = None
    lastClose: Any = None
    nativeVolume: Any = None
    nativeAmount: Any = None
    eventTime: Any = None
    error_id: Any = None
    code: Any = None


def extract_tdx_snapshot_native_fields(
    native: Mapping[str, Any],
) -> RawTdxSnapshotFields:
    """Project native aliases without applying a consumer-specific policy.

    Each provider field is projected independently. This preserves the
    historical HTTP behavior while allowing the realtime validator to apply
    a separate logical-alias policy after its strict conflict check.
    """
    values = {
        logical: native_value(native, *aliases)
        for logical, aliases in TDX_SNAPSHOT_FIELD_ALIASES.items()
    }
    return RawTdxSnapshotFields(
        now=values["now"],
        last=values["last"],
        close=values["close"],
        open=values["open"],
        maximum=values["maximum"],
        high=values["high"],
        minimum=values["minimum"],
        low=values["low"],
        lastClose=values["lastClose"],
        nativeVolume=values["nativeVolume"],
        nativeAmount=values["nativeAmount"],
        eventTime=values["eventTime"],
        error_id=native_value(native, "ErrorId", "errorid", "error_id"),
        code=native_value(native, "Code", "code"),
    )


def normalize_symbol(code: str) -> str:
    value = code.strip().upper()
    if len(value) >= 8 and value[:2] in {"SH", "SZ"}:
        return f"{value[2:]}.{value[:2]}"
    if "." in value:
        stock_code, market = value.split(".", 1)
        return f"{stock_code}.{market}"
    return value


def dedupe_stable(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def dedupe_normalized_symbols(symbols: Iterable[str]) -> list[str]:
    return dedupe_stable(normalize_symbol(symbol) for symbol in symbols)


def to_tdx_code(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if "." not in normalized:
        return normalized
    stock_code, market = normalized.split(".", 1)
    return f"{market}{stock_code}"


def to_tdx_http_code(symbol: str) -> str:
    return normalize_symbol(symbol)


def beijing_iso(value: str | datetime | None = None) -> str:
    if value is None:
        value = datetime.now(BEIJING_TZ)
    normalized = normalize_beijing_iso(value)
    if normalized is None:
        msg = "beijing_iso cannot normalize None after current time fallback"
        raise ValueError(msg)
    return normalized


def normalize_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def normalize_optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return float(value)


def normalize_native_key(value: Any) -> str:
    return str(value).replace("_", "").replace(" ", "").lower()


def native_value(native: Mapping[str, Any], *field_names: str) -> Any:
    expected_keys = {normalize_native_key(field_name) for field_name in field_names}
    for key, value in native.items():
        if normalize_native_key(key) in expected_keys:
            return value
    return None


def normalize_tdx_bar_rows(symbol: str, period: str, native: dict[str, Any]) -> list[TdxBar]:
    normalized_symbol = normalize_symbol(symbol)
    open_values = _series_for_symbol(native, "open", normalized_symbol)
    high_values = _series_for_symbol(native, "high", normalized_symbol)
    low_values = _series_for_symbol(native, "low", normalized_symbol)
    close_values = _series_for_symbol(native, "close", normalized_symbol)
    volume_values = _series_for_symbol(native, "volume", normalized_symbol)
    amount_values = _series_for_symbol(native, "amount", normalized_symbol)
    forward_factor_values = _series_for_symbol(native, "ForwardFactor", normalized_symbol)
    vol_in_stock_values = _series_for_symbol(native, "VolInStock", normalized_symbol)

    timestamps = sorted(
        set[str]().union(
            open_values,
            high_values,
            low_values,
            close_values,
            volume_values,
            amount_values,
            forward_factor_values,
            vol_in_stock_values,
        )
    )

    return [
        TdxBar(
            symbol=normalized_symbol,
            period=period,
            barTime=beijing_iso(timestamp),
            open=normalize_number(open_values.get(timestamp)),
            high=normalize_number(high_values.get(timestamp)),
            low=normalize_number(low_values.get(timestamp)),
            close=normalize_number(close_values.get(timestamp)),
            volume=normalize_number(volume_values.get(timestamp)),
            amount=normalize_number(amount_values.get(timestamp)),
            forwardFactor=normalize_optional_number(forward_factor_values.get(timestamp)),
            volInStock=normalize_optional_number(vol_in_stock_values.get(timestamp)),
            provider="tdx",
            receivedAt=beijing_iso(),
        )
        for timestamp in timestamps
    ]


def normalize_tdx_snapshot(symbol: str, native: dict[str, Any]) -> TdxSnapshot:
    normalized_symbol = normalize_symbol(symbol)
    raw = extract_tdx_snapshot_native_fields(native)

    return TdxSnapshot(
        symbol=normalized_symbol,
        # Formal HTTP semantics are intentionally frozen to the historical
        # provider fields. Realtime-only aliases must not leak here.
        last=normalize_number(raw.now),
        open=normalize_number(raw.open),
        high=normalize_number(raw.maximum),
        low=normalize_number(raw.minimum),
        lastClose=normalize_number(raw.lastClose),
        volume=normalize_number(raw.nativeVolume),
        amount=normalize_number(raw.nativeAmount),
        provider="tdx",
        asOf=beijing_iso(raw.eventTime),
    )


def _series_for_symbol(
    native: dict[str, Any],
    field_name: str,
    normalized_symbol: str,
) -> dict[str, Any]:
    field_map = _get_native_value(native, field_name)

    candidate_keys = (
        to_tdx_code(normalized_symbol),
        normalized_symbol,
        normalized_symbol.lower(),
        to_tdx_code(normalized_symbol).lower(),
    )

    if _looks_like_dataframe(field_map):
        return _dataframe_row_for_symbol(field_map, candidate_keys)

    if isinstance(field_map, dict):
        field_mapping = cast(dict[str, Any], field_map)
        for key in candidate_keys:
            values = field_mapping.get(key)
            if isinstance(values, dict):
                return cast(dict[str, Any], values)

    symbol_values = _symbol_values_from_symbol_wrapper(native, candidate_keys)
    if isinstance(symbol_values, dict):
        return _array_series_for_field(symbol_values, field_name)

    symbol_values = _symbol_values_from_value_wrapper(native, candidate_keys)
    if isinstance(symbol_values, dict):
        return _array_series_for_field(symbol_values, field_name)

    return {}


def _looks_like_dataframe(value: Any) -> bool:
    return all(hasattr(value, attr) for attr in ("loc", "index", "columns"))


def _dataframe_row_for_symbol(field_value: Any, candidate_keys: tuple[str, ...]) -> dict[str, Any]:
    index_values = {str(index_value) for index_value in field_value.index}
    for key in candidate_keys:
        if key not in index_values:
            continue
        row = field_value.loc[key]
        if hasattr(row, "to_dict"):
            return cast(dict[str, Any], row.to_dict())
        return dict(row)
    return {}


def _symbol_values_from_symbol_wrapper(
    native: dict[str, Any], candidate_keys: tuple[str, ...]
) -> dict[str, Any] | None:
    for key in candidate_keys:
        values = native.get(key)
        if isinstance(values, dict):
            return cast(dict[str, Any], values)

    normalized_candidates = {key.upper() for key in candidate_keys}
    for key, values in native.items():
        if str(key).upper() in normalized_candidates and isinstance(values, dict):
            return cast(dict[str, Any], values)

    return None


def _symbol_values_from_value_wrapper(
    native: dict[str, Any], candidate_keys: tuple[str, ...]
) -> dict[str, Any] | None:
    value_wrapper = _get_native_value(native, "value")
    if not isinstance(value_wrapper, dict):
        return None
    value_mapping = cast(dict[str, Any], value_wrapper)

    for key in candidate_keys:
        values = value_mapping.get(key)
        if isinstance(values, dict):
            return cast(dict[str, Any], values)

    normalized_candidates = {key.upper() for key in candidate_keys}
    for key, values in value_mapping.items():
        if str(key).upper() in normalized_candidates and isinstance(values, dict):
            return cast(dict[str, Any], values)

    return None


def _array_series_for_field(symbol_values: dict[str, Any], field_name: str) -> dict[str, Any]:
    field_values = _get_native_value(symbol_values, field_name)
    if not isinstance(field_values, list | tuple):
        return {}
    field_sequence = cast(list[Any] | tuple[Any, ...], field_values)

    dates = _as_sequence(_get_native_value(symbol_values, "date"))
    times = _as_sequence(_get_native_value(symbol_values, "time"))

    series: dict[str, Any] = {}
    for index, value in enumerate(field_sequence):
        timestamp = _tdx_array_timestamp(_value_at(dates, index), _value_at(times, index))
        if timestamp:
            series[timestamp] = value
    return series


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(cast(list[Any] | tuple[Any, ...], value))
    return []


def _value_at(values: list[Any], index: int) -> Any:
    if index < len(values):
        return values[index]
    return None


def _tdx_array_timestamp(date_value: Any, time_value: Any) -> str | None:
    if date_value is None:
        return None

    date_text = str(date_value).strip()
    if len(date_text) == 8 and date_text.isdigit():
        date_text = f"{date_text[0:4]}-{date_text[4:6]}-{date_text[6:8]}"

    time_text = "" if time_value is None else str(time_value).strip()
    if not time_text or time_text == "0":
        return f"{date_text}T00:00:00"

    if time_text.isdigit():
        if len(time_text) <= 4:
            digits = time_text.zfill(4)
            return f"{date_text}T{digits[0:2]}:{digits[2:4]}:00"
        digits = time_text.zfill(6)
        return f"{date_text}T{digits[0:2]}:{digits[2:4]}:{digits[4:6]}"

    return f"{date_text}T{time_text}"


def _get_native_value(native: dict[str, Any], field_name: str) -> Any:
    return native_value(native, field_name)
