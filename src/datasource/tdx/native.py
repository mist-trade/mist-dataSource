from typing import Any, cast

from src.datasource.tdx.errors import TdxSymbolNotFoundError
from src.datasource.tdx_normalization import (
    native_value,
    normalize_native_key,
    normalize_optional_number,
    normalize_symbol,
    to_tdx_code,
    to_tdx_http_code,
)


def unwrap_tdx_value(native: Any) -> Any:
    native_mapping_value = native_mapping(native)
    if native_mapping_value is None:
        return native
    for key, value in native_mapping_value.items():
        if normalize_native_key(key) == "value":
            return value
    return native_mapping_value


def native_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return None


def native_sequence(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(cast(list[Any] | tuple[Any, ...], value))
    return []


def native_record(value: Any) -> dict[str, Any]:
    return native_mapping(value) or {"value": value}


def native_items(native: Any, *preferred_list_fields: str) -> list[Any]:
    values = unwrap_tdx_value(native)
    if isinstance(values, list | tuple):
        return native_sequence(values)
    values_mapping = native_mapping(values)
    if values_mapping is not None:
        for field_name in preferred_list_fields:
            field_value = first_native_value(values_mapping, field_name)
            field_sequence = native_sequence(field_value)
            if field_sequence:
                return field_sequence
        return [values_mapping]
    if values is None:
        return []
    return [values]


def native_item_for_symbol(native: Any, symbol: str) -> Any:
    values = unwrap_tdx_value(native)
    normalized_symbol = normalize_symbol(symbol)
    candidates = code_candidates(normalized_symbol)
    values_mapping = native_mapping(values)
    if values_mapping is not None:
        for key, value in values_mapping.items():
            if str(key).upper() in candidates:
                return value
        if native_record_matches_symbol(values_mapping, candidates):
            return values_mapping
        raise TdxSymbolNotFoundError(symbol=normalized_symbol, native=native)
    for item in native_sequence(values):
        item_mapping = native_mapping(item)
        if item_mapping is not None and native_record_matches_symbol(item_mapping, candidates):
            return item_mapping
    if native_sequence(values):
        raise TdxSymbolNotFoundError(symbol=normalized_symbol, native=native)
    raise TdxSymbolNotFoundError(symbol=normalized_symbol, native=native)


def as_sequence(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list | tuple):
        return native_sequence(value)
    return [value]


def record_for_code(values: Any, code: str | None) -> Any:
    values_mapping = native_mapping(values)
    if code is None:
        return values_mapping or {}
    if values_mapping is None:
        return values

    candidates = code_candidates(code)
    for key, value in values_mapping.items():
        if str(key).upper() in candidates:
            return value
    return values_mapping


def lookup_symbol_field(values: Any, symbol: str, field_name: str) -> Any:
    values_mapping = native_mapping(values)
    if values_mapping is None:
        return values

    symbol_record = record_for_code(values_mapping, symbol)
    symbol_mapping = native_mapping(symbol_record)
    if symbol_mapping is not None:
        direct_value = first_native_value(symbol_mapping, field_name)
        if direct_value is not None:
            if symbol_record is values_mapping and native_mapping(direct_value) is not None:
                nested_value = record_for_code(direct_value, symbol)
                if nested_value is not direct_value:
                    return nested_value
            return direct_value

    field_record = first_native_value(values_mapping, field_name)
    if native_mapping(field_record) is not None:
        symbol_value = record_for_code(field_record, symbol)
        if symbol_value is not field_record:
            return symbol_value

    if symbol_record is not values_mapping:
        return symbol_record
    return first_native_value(values_mapping, field_name)


def lookup_aggregate_value(values: Any, code: str | None, field_name: str) -> Any:
    values_mapping = native_mapping(values)
    if values_mapping is None:
        return values
    if code is None:
        return first_native_value(values_mapping, field_name)

    code_record = record_for_code(values_mapping, code)
    code_mapping = native_mapping(code_record)
    if code_mapping is not None:
        direct_value = first_native_value(code_mapping, field_name)
        if direct_value is not None:
            return direct_value

    field_record = first_native_value(values_mapping, field_name)
    if native_mapping(field_record) is not None:
        code_value = record_for_code(field_record, code)
        if code_value is not field_record:
            return code_value
    return None


def code_candidates(code: str) -> set[str]:
    return {
        str(code).upper(),
        normalize_symbol(str(code)).upper(),
        to_tdx_http_code(str(code)).upper(),
        to_tdx_code(str(code)).upper(),
    }


def native_record_matches_symbol(record: dict[str, Any], candidates: set[str]) -> bool:
    item_symbol = first_native_value(record, "symbol", "code", "stock_code", "Code")
    if item_symbol is None:
        return False
    return normalize_symbol(str(item_symbol)).upper() in candidates


def metadata_value(record: Any, field_name: str) -> str | None:
    record_mapping = native_mapping(record)
    if record_mapping is None:
        return None
    value = first_native_value(record_mapping, field_name)
    return str(value) if value is not None else None


def scalar_value(value: Any) -> Any:
    if isinstance(value, list | tuple):
        value_sequence = native_sequence(value)
        return [scalar_value(item) for item in value_sequence]
    value_mapping = native_mapping(value)
    if value_mapping is not None:
        return value_mapping
    numeric_value = optional_float(value)
    if numeric_value is not None:
        return numeric_value
    return value


def aggregate_events(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        value_sequence = native_sequence(value)
        if not value_sequence:
            return []
        if any(native_mapping(item) is not None for item in value_sequence):
            return value_sequence
        return [value_sequence]
    return [value]


def aggregate_event_parts(event: Any) -> tuple[Any | None, Any]:
    event_mapping = native_mapping(event)
    if event_mapping is not None:
        date = first_native_value(event_mapping, "Date", "date")
        raw_values = first_native_value(event_mapping, "Value", "value", "values")
        if raw_values is None:
            raw_values = {
                key: value
                for key, value in event_mapping.items()
                if normalize_native_key(key) != "date"
            }
        return date, raw_values
    return None, event


def normalize_aggregate_code(scope: str, code: str | None) -> str | None:
    if code is None:
        return None
    if scope == "stock":
        return normalize_symbol(code)
    return str(code)


def numeric_values(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        value_sequence = native_sequence(value)
        return [scalar_value(item) for item in value_sequence]
    value_mapping = native_mapping(value)
    if value_mapping is not None:
        return [scalar_value(item) for item in value_mapping.values()]
    return [scalar_value(value)]


def first_native_value(native: dict[str, Any], *field_names: str) -> Any:
    return native_value(native, *field_names)


def optional_float(value: Any) -> float | None:
    try:
        return normalize_optional_number(value)
    except (TypeError, ValueError):
        return None


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes"}:
        return True
    if text in {"0", "false", "no"}:
        return False
    return None
