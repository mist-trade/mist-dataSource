from typing import Any

from src.datasource.tdx.native import (
    as_sequence,
    first_native_value,
    native_items,
    native_mapping,
    native_record,
    native_sequence,
    optional_float,
    unwrap_tdx_value,
)
from src.datasource.tdx_normalization import normalize_symbol


def normalize_security_item(item: Any) -> dict[str, Any]:
    item_mapping = native_mapping(item)
    if item_mapping is not None:
        symbol = first_native_value(item_mapping, "symbol", "code", "stock_code", "Code")
        name = first_native_value(item_mapping, "name", "Name", "stock_name")
        return {
            "symbol": normalize_symbol(str(symbol)) if symbol else "",
            "name": str(name) if name is not None else None,
            "provider": "tdx",
            "raw": item,
        }
    item_sequence = native_sequence(item)
    if item_sequence:
        symbol = str(item_sequence[0])
        name = str(item_sequence[1]) if len(item_sequence) > 1 else None
        return {
            "symbol": normalize_symbol(symbol),
            "name": name,
            "provider": "tdx",
            "raw": item_sequence,
        }
    return {
        "symbol": normalize_symbol(str(item)),
        "name": None,
        "provider": "tdx",
    }


def normalize_security_info(
    symbol: str,
    stock_info: Any,
    more_info: Any,
) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "stockInfo": stock_info,
        "moreInfo": more_info,
    }
    stock_info_dict = native_mapping(stock_info) or {}
    more_info_dict = native_mapping(more_info) or {}
    name = first_native_value(stock_info_dict, "name", "Name", "stock_name")
    market = first_native_value(stock_info_dict, "market", "Market")
    if market is None:
        normalized_symbol = normalize_symbol(symbol)
        market = normalized_symbol.split(".", 1)[1] if "." in normalized_symbol else None
    return {
        "symbol": normalize_symbol(symbol),
        "name": str(name) if name is not None else None,
        "market": str(market) if market is not None else None,
        "provider": "tdx",
        "raw": raw,
        "more": more_info_dict,
    }


def normalize_relation_items(symbol: str, native: Any) -> list[dict[str, Any]]:
    values = unwrap_tdx_value(native)
    relations: list[dict[str, Any]] = []

    values_mapping = native_mapping(values)
    if values_mapping is not None:
        sector_values = first_native_value(
            values_mapping, "RelatedSectors", "sectors", "sector_list"
        )
        stock_values = first_native_value(values_mapping, "RelatedStocks", "stocks", "stock_list")
        if sector_values is not None or stock_values is not None:
            relations.extend(
                _normalize_relation_group(symbol, "sector", as_sequence(sector_values))
            )
            relations.extend(_normalize_relation_group(symbol, "stock", as_sequence(stock_values)))
            return relations
        return [_normalize_relation_item(symbol, values_mapping, "unknown")]

    return _normalize_relation_group(symbol, "unknown", as_sequence(values))


def _normalize_relation_group(
    symbol: str,
    category: str,
    values: list[Any],
) -> list[dict[str, Any]]:
    return [_normalize_relation_item(symbol, item, category) for item in values]


def _normalize_relation_item(
    symbol: str,
    item: Any,
    default_category: str,
) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    item_mapping = native_mapping(item)
    if item_mapping is not None:
        code = first_native_value(item_mapping, "code", "Code", "block_code", "stock_code")
        name = first_native_value(item_mapping, "name", "Name", "block_name")
        category = first_native_value(item_mapping, "category", "Type", "type")
        return {
            "symbol": normalized_symbol,
            "category": str(category) if category is not None else default_category,
            "code": str(code) if code is not None else "",
            "name": str(name) if name is not None else None,
            "provider": "tdx",
            "raw": item,
        }
    return {
        "symbol": normalized_symbol,
        "category": default_category,
        "code": normalize_symbol(str(item)) if default_category == "stock" else str(item),
        "name": None,
        "provider": "tdx",
        "raw": item,
    }


def normalize_ipo_item(item: Any) -> dict[str, Any]:
    native = native_record(item)
    code = first_native_value(native, "code", "Code")
    name = first_native_value(native, "name", "Name")
    subscribe_code = first_native_value(native, "SGCode", "subscribeCode")
    subscribe_date = first_native_value(native, "SGDate", "subscribeDate")
    issue_price = first_native_value(native, "SGPrice", "issuePrice")
    return {
        "code": str(code) if code is not None else "",
        "name": str(name) if name is not None else None,
        "subscribeCode": str(subscribe_code) if subscribe_code is not None else None,
        "subscribeDate": str(subscribe_date) if subscribe_date is not None else None,
        "issuePrice": optional_float(issue_price),
        "provider": "tdx",
        "raw": item,
    }


def normalize_share_capital_item(symbol: str, item: Any) -> dict[str, Any]:
    native = native_record(item)
    date = first_native_value(native, "Date", "date")
    total_share_capital = first_native_value(native, "Zgb", "TotalShare", "totalShareCapital")
    float_share_capital = first_native_value(native, "Ltgb", "FlowShare", "floatShareCapital")
    return {
        "symbol": normalize_symbol(symbol),
        "date": str(date) if date is not None else None,
        "totalShareCapital": optional_float(total_share_capital),
        "floatShareCapital": optional_float(float_share_capital),
        "provider": "tdx",
        "raw": item,
    }


def normalize_dividend_factor_item(symbol: str, item: Any) -> dict[str, Any]:
    native = native_record(item)
    date = first_native_value(native, "Date", "date")
    factor_type = first_native_value(native, "Type", "type")
    bonus = first_native_value(native, "Bonus", "bonus")
    allot_price = first_native_value(native, "AlloPrice", "AllotPrice", "allotPrice")
    share_bonus = first_native_value(native, "ShareBonus", "shareBonus")
    allotment = first_native_value(native, "Allotment", "allotment")
    return {
        "symbol": normalize_symbol(symbol),
        "date": str(date) if date is not None else None,
        "type": str(factor_type) if factor_type is not None else None,
        "bonus": optional_float(bonus),
        "allotPrice": optional_float(allot_price),
        "shareBonus": optional_float(share_bonus),
        "allotment": optional_float(allotment),
        "provider": "tdx",
        "raw": item,
    }


def normalize_convertible_bond_item(symbol: str, item: Any) -> dict[str, Any]:
    native = native_record(item)
    bond_code = first_native_value(native, "KZZCode", "Code", "code", "stock_code")
    underlying_symbol = first_native_value(native, "HSCode", "underlyingSymbol")
    convert_price = first_native_value(native, "ZGPrice", "convertPrice")
    bond_price = first_native_value(native, "KZZPrice", "bondPrice")
    underlying_price = first_native_value(native, "AGPrice", "underlyingPrice")
    premium_rate = first_native_value(native, "KZZYj", "premiumRate")
    convert_value = first_native_value(native, "ZGValue", "convertValue")
    remaining_size = first_native_value(native, "RestScope", "remainingSize")
    return {
        "symbol": normalize_symbol(symbol),
        "bondCode": str(bond_code) if bond_code is not None else None,
        "underlyingSymbol": str(underlying_symbol) if underlying_symbol is not None else None,
        "convertPrice": optional_float(convert_price),
        "bondPrice": optional_float(bond_price),
        "underlyingPrice": optional_float(underlying_price),
        "premiumRate": optional_float(premium_rate),
        "convertValue": optional_float(convert_value),
        "remainingSize": optional_float(remaining_size),
        "provider": "tdx",
        "raw": item,
    }


def normalize_tracking_etf_item(index_symbol: str, item: Any) -> dict[str, Any]:
    native = native_record(item)
    code = first_native_value(native, "Code", "code")
    name = first_native_value(native, "Name", "name")
    price = first_native_value(native, "NowPrice", "price")
    pre_close = first_native_value(native, "PreClose", "preClose")
    iopv = first_native_value(native, "IOPV", "iopv")
    fund_size = first_native_value(native, "Sz", "size")
    return {
        "indexSymbol": index_symbol,
        "symbol": normalize_symbol(str(code)) if code is not None else "",
        "name": str(name) if name is not None else None,
        "price": optional_float(price),
        "preClose": optional_float(pre_close),
        "iopv": optional_float(iopv),
        "size": optional_float(fund_size),
        "provider": "tdx",
        "raw": item,
    }


def extract_native_items(native: Any, *preferred_list_fields: str) -> list[Any]:
    return native_items(native, *preferred_list_fields)
