from typing import Any

from src.datasource.tdx.native import (
    first_native_value,
    native_mapping,
    native_sequence,
    unwrap_tdx_value,
)
from src.datasource.tdx_normalization import normalize_symbol


def normalize_sector_item(item: Any) -> dict[str, Any]:
    item_mapping = native_mapping(item)
    if item_mapping is not None:
        code = first_native_value(item_mapping, "code", "Code", "block_code", "BlockCode")
        name = first_native_value(item_mapping, "name", "Name", "block_name", "BlockName")
        return {
            "code": str(code) if code is not None else "",
            "name": str(name) if name is not None else None,
            "provider": "tdx",
            "raw": item,
        }
    item_sequence = native_sequence(item)
    if item_sequence:
        return {
            "code": str(item_sequence[0]),
            "name": str(item_sequence[1]) if len(item_sequence) > 1 else None,
            "provider": "tdx",
            "raw": item_sequence,
        }
    return {
        "code": str(item),
        "name": None,
        "provider": "tdx",
    }


def normalize_sector_members(native: Any) -> list[str]:
    members = unwrap_tdx_value(native)
    return [normalize_symbol(str(symbol)) for symbol in native_sequence(members)]
