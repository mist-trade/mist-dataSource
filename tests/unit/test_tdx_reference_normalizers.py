"""Direct tests for TDX reference/security normalizers."""

from __future__ import annotations

from src.datasource.tdx.normalizers.reference import (
    normalize_convertible_bond_item,
    normalize_dividend_factor_item,
    normalize_ipo_item,
    normalize_relation_items,
    normalize_security_info,
    normalize_security_item,
    normalize_share_capital_item,
    normalize_tracking_etf_item,
)


def test_normalize_security_item_accepts_mapping_and_sequence_shapes() -> None:
    assert normalize_security_item({"Code": "SH600519", "Name": "贵州茅台"}) == {
        "symbol": "600519.SH",
        "name": "贵州茅台",
        "provider": "tdx",
        "raw": {"Code": "SH600519", "Name": "贵州茅台"},
    }
    assert normalize_security_item(("000001.SZ", "平安银行")) == {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "provider": "tdx",
        "raw": ["000001.SZ", "平安银行"],
    }


def test_normalize_security_info_combines_stock_and_more_info() -> None:
    item = normalize_security_info(
        "600519.SH",
        {"Name": "贵州茅台", "Market": "SH"},
        {"Industry": "白酒"},
    )

    assert item["symbol"] == "600519.SH"
    assert item["name"] == "贵州茅台"
    assert item["market"] == "SH"
    assert item["more"] == {"Industry": "白酒"}


def test_normalize_relation_items_accepts_grouped_native_shape() -> None:
    items = normalize_relation_items(
        "600519.SH",
        {
            "Value": {
                "RelatedSectors": [{"Code": "880081.SH", "Name": "通达信88"}],
                "RelatedStocks": ["SH600000"],
            }
        },
    )

    assert items == [
        {
            "symbol": "600519.SH",
            "category": "sector",
            "code": "880081.SH",
            "name": "通达信88",
            "provider": "tdx",
            "raw": {"Code": "880081.SH", "Name": "通达信88"},
        },
        {
            "symbol": "600519.SH",
            "category": "stock",
            "code": "600000.SH",
            "name": None,
            "provider": "tdx",
            "raw": "SH600000",
        },
    ]


def test_normalize_reference_instrument_items() -> None:
    assert (
        normalize_ipo_item(
            {"Code": "301036", "Name": "双乐转债", "SGCode": "371036", "SGPrice": "100.00"}
        )["issuePrice"]
        == 100.0
    )
    assert (
        normalize_share_capital_item(
            "600519.SH",
            {"Date": 20250101, "Zgb": "182942480", "Ltgb": "182942480"},
        )["totalShareCapital"]
        == 182942480.0
    )
    assert (
        normalize_dividend_factor_item(
            "600519.SH",
            {"Date": "20250101", "Bonus": "1.23", "ShareBonus": "0.5"},
        )["shareBonus"]
        == 0.5
    )
    assert (
        normalize_convertible_bond_item(
            "123039.SZ",
            {"KZZCode": "123039", "HSCode": "300577", "ZGPrice": "29.15"},
        )["convertPrice"]
        == 29.15
    )
    assert (
        normalize_tracking_etf_item(
            "950162.CSI",
            {"Code": "510300.SH", "Name": "沪深300ETF", "NowPrice": "4.21"},
        )["symbol"]
        == "510300.SH"
    )
