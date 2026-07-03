from typing import Any

from src.datasource.tdx.native import (
    aggregate_event_parts,
    aggregate_events,
    lookup_aggregate_value,
    lookup_symbol_field,
    metadata_value,
    normalize_aggregate_code,
    numeric_values,
    record_for_code,
    scalar_value,
    unwrap_tdx_value,
)
from src.datasource.tdx_normalization import normalize_symbol


def normalize_financial_data_items(
    symbols: list[str],
    fields: list[str],
    native: Any,
) -> list[dict[str, Any]]:
    values = unwrap_tdx_value(native)
    items: list[dict[str, Any]] = []

    for symbol in symbols:
        raw_record = record_for_code(values, symbol)
        for field_name in fields:
            field_value = lookup_symbol_field(values, symbol, field_name)
            if field_value is None:
                continue
            items.append(
                {
                    "symbol": normalize_symbol(symbol),
                    "field": field_name,
                    "value": scalar_value(field_value),
                    "announceTime": metadata_value(raw_record, "announce_time"),
                    "tagTime": metadata_value(raw_record, "tag_time"),
                    "provider": "tdx",
                    "raw": raw_record,
                }
            )

    return items


def normalize_single_finance_value_items(
    symbols: list[str],
    fields: list[str],
    native: Any,
) -> list[dict[str, Any]]:
    values = unwrap_tdx_value(native)
    items: list[dict[str, Any]] = []
    for symbol in symbols:
        for field_name in fields:
            field_value = lookup_symbol_field(values, symbol, field_name)
            if field_value is None:
                continue
            items.append(
                {
                    "symbol": normalize_symbol(symbol),
                    "field": field_name,
                    "value": scalar_value(field_value),
                    "provider": "tdx",
                    "raw": values,
                }
            )
    return items


def normalize_trade_aggregate_items(
    scope: str,
    codes: list[str] | list[str | None],
    fields: list[str],
    native: Any,
) -> list[dict[str, Any]]:
    values = unwrap_tdx_value(native)
    items: list[dict[str, Any]] = []
    for code in codes:
        for field_name in fields:
            native_value = lookup_aggregate_value(values, code, field_name)
            if native_value is None:
                continue
            for event in aggregate_events(native_value):
                date, raw_values = aggregate_event_parts(event)
                items.append(
                    {
                        "scope": scope,
                        "code": normalize_aggregate_code(scope, code),
                        "field": field_name,
                        "date": str(date) if date is not None else None,
                        "values": numeric_values(raw_values),
                        "provider": "tdx",
                        "raw": event,
                    }
                )
    return items
