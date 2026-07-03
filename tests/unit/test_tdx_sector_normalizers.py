"""Direct tests for TDX sector normalizers."""

from __future__ import annotations

from src.datasource.tdx.normalizers.sector import (
    normalize_sector_item,
    normalize_sector_members,
)


def test_normalize_sector_item_accepts_mapping_sequence_and_scalar_shapes() -> None:
    assert normalize_sector_item({"Code": "880081.SH", "Name": "通达信88"}) == {
        "code": "880081.SH",
        "name": "通达信88",
        "provider": "tdx",
        "raw": {"Code": "880081.SH", "Name": "通达信88"},
    }
    assert normalize_sector_item(("880300.SH", "沪深300")) == {
        "code": "880300.SH",
        "name": "沪深300",
        "provider": "tdx",
        "raw": ["880300.SH", "沪深300"],
    }
    assert normalize_sector_item("880660.SH") == {
        "code": "880660.SH",
        "name": None,
        "provider": "tdx",
    }


def test_normalize_sector_members_accepts_value_wrappers_and_normalizes_symbols() -> None:
    assert normalize_sector_members({"Value": ["SH600519", "000001.SZ"]}) == [
        "600519.SH",
        "000001.SZ",
    ]
