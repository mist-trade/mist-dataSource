"""Direct tests for TDX finance and trade aggregate normalizers."""

from __future__ import annotations

from src.datasource.tdx.normalizers.finance import (
    normalize_financial_data_items,
    normalize_single_finance_value_items,
    normalize_trade_aggregate_items,
)


def test_normalize_financial_data_items_flattens_symbol_records() -> None:
    items = normalize_financial_data_items(
        ["600519.SH"],
        ["FN193", "FN194"],
        {
            "Value": {
                "600519.SH": {
                    "FN193": "162.47",
                    "FN194": "69.67",
                    "announce_time": "20250331",
                    "tag_time": "20241231",
                }
            }
        },
    )

    assert items[0]["symbol"] == "600519.SH"
    assert items[0]["field"] == "FN193"
    assert items[0]["value"] == 162.47
    assert items[0]["announceTime"] == "20250331"
    assert items[1]["field"] == "FN194"


def test_normalize_single_finance_value_items_accepts_field_first_shape() -> None:
    items = normalize_single_finance_value_items(
        ["688318.SH"],
        ["GO1", "GO2"],
        {
            "Value": {
                "GO1": {"688318.SH": "107.41"},
                "GO2": {"688318.SH": "3.12"},
            }
        },
    )

    assert [item["field"] for item in items] == ["GO1", "GO2"]
    assert [item["value"] for item in items] == [107.41, 3.12]


def test_normalize_trade_aggregate_items_handles_stock_scope_events() -> None:
    items = normalize_trade_aggregate_items(
        "stock",
        ["688318.SH"],
        ["GP3"],
        {
            "Value": {
                "688318.SH": {"GP3": [{"Date": "20250102", "Value": ["141405.89", "11113.00"]}]}
            }
        },
    )

    assert items == [
        {
            "scope": "stock",
            "code": "688318.SH",
            "field": "GP3",
            "date": "20250102",
            "values": [141405.89, 11113.0],
            "provider": "tdx",
            "raw": {"Date": "20250102", "Value": ["141405.89", "11113.00"]},
        }
    ]


def test_normalize_trade_aggregate_items_handles_market_scope_without_code() -> None:
    items = normalize_trade_aggregate_items(
        "market",
        [None],
        ["SC1"],
        {"Value": {"SC1": [{"Date": "20250102", "Value": ["184712288"]}]}},
    )

    assert items[0]["scope"] == "market"
    assert items[0]["code"] is None
    assert items[0]["values"] == [184712288.0]
