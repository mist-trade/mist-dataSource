"""Direct tests for shared TDX native response helper functions."""

from __future__ import annotations

import pytest

from src.datasource.tdx.errors import TdxSymbolNotFoundError
from src.datasource.tdx.native import (
    as_sequence,
    native_item_for_symbol,
    native_items,
    native_mapping,
    native_sequence,
    scalar_value,
    unwrap_tdx_value,
)


def test_unwrap_tdx_value_accepts_case_insensitive_value_wrapper() -> None:
    assert unwrap_tdx_value({"ErrorId": "0", "Value": [1, 2]}) == [1, 2]
    assert unwrap_tdx_value({"error_id": "0", "value": {"x": 1}}) == {"x": 1}


def test_native_mapping_sequence_and_as_sequence_are_shape_safe() -> None:
    assert native_mapping({"x": 1}) == {"x": 1}
    assert native_mapping([("x", 1)]) is None
    assert native_sequence(("a", "b")) == ["a", "b"]
    assert native_sequence({"x": 1}) == []
    assert as_sequence(None) == []
    assert as_sequence("600519.SH") == ["600519.SH"]


def test_native_items_prefers_named_list_fields_and_wraps_scalars() -> None:
    assert native_items({"Value": {"Rows": [{"Code": "600519"}]}}, "Rows") == [{"Code": "600519"}]
    assert native_items({"Value": ["600519.SH"]}) == ["600519.SH"]
    assert native_items({"Value": "600519.SH"}) == ["600519.SH"]


def test_native_item_for_symbol_matches_wrappers_and_rejects_missing_symbol() -> None:
    native = {
        "Value": {
            "000001.SZ": {"Now": "10"},
            "SH600519": {"Now": "1688"},
        }
    }

    assert native_item_for_symbol(native, "600519.SH") == {"Now": "1688"}

    with pytest.raises(TdxSymbolNotFoundError) as exc_info:
        native_item_for_symbol(native, "300750.SZ")

    assert exc_info.value.code == "TDX_SYMBOL_NOT_FOUND"
    assert exc_info.value.details["symbol"] == "300750.SZ"


def test_scalar_value_converts_numbers_but_preserves_non_numeric_shapes() -> None:
    assert scalar_value("12.34") == 12.34
    assert scalar_value(["1", "2.5"]) == [1.0, 2.5]
    assert scalar_value({"raw": "x"}) == {"raw": "x"}
    assert scalar_value("not-a-number") == "not-a-number"
