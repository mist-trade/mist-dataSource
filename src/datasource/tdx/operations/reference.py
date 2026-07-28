from typing import Any

from src.datasource.tdx.http_client import TdxHttpClient
from src.datasource.tdx.market_normalization import to_tdx_http_code
from src.datasource.tdx.native import (
    first_native_value,
    native_items,
    native_mapping,
    native_sequence,
    unwrap_tdx_value,
)
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


class TdxReferenceOperations:
    def __init__(self, client: TdxHttpClient) -> None:
        self.client = client

    async def get_trading_dates(
        self,
        market: str,
        start_time: str | None = None,
        end_time: str | None = None,
        count: int | None = None,
    ) -> list[str]:
        native = await self.client.call(
            "get_trading_dates",
            {
                "market": market,
                "start_time": start_time or "",
                "end_time": end_time or "",
                "count": count if count is not None else -1,
            },
        )
        values = unwrap_tdx_value(native)
        values_mapping = native_mapping(values)
        if values_mapping is not None:
            values = first_native_value(values_mapping, "Date", "date", "tradingDates", "dates")
        values_sequence = native_sequence(values)
        if values_sequence:
            return [_normalize_trading_date(value) for value in values_sequence]
        return []

    async def get_securities(self, market: str = "5") -> list[dict[str, Any]]:
        native = await self.client.call("get_stock_list", {"market": market, "list_type": 1})
        values = unwrap_tdx_value(native)
        return [normalize_security_item(item) for item in native_sequence(values)]

    async def get_security_info(self, symbols: list[str]) -> list[dict[str, Any]]:
        securities: list[dict[str, Any]] = []
        for symbol in symbols:
            tdx_symbol = to_tdx_http_code(symbol)
            stock_info = await self.client.call("get_stock_info", {"stock_code": tdx_symbol})
            more_info = await self.client.call(
                "get_more_info",
                {
                    "stock_code": tdx_symbol,
                    "field_list": [],
                },
            )
            securities.append(normalize_security_info(tdx_symbol, stock_info, more_info))
        return securities

    async def get_security_relations(self, symbol: str) -> list[dict[str, Any]]:
        tdx_symbol = to_tdx_http_code(symbol)
        native = await self.client.call("get_relation", {"stock_code": tdx_symbol})
        return normalize_relation_items(tdx_symbol, native)

    async def get_ipo_info(self, ipo_type: int = 0, ipo_date: int = 0) -> list[dict[str, Any]]:
        native = await self.client.call(
            "get_ipo_info",
            {
                "ipo_type": ipo_type,
                "ipo_date": ipo_date,
            },
        )
        return [normalize_ipo_item(item) for item in native_items(native, "IPOStocks")]

    async def get_share_capital(
        self,
        symbol: str,
        date_list: list[str],
        count: int,
    ) -> list[dict[str, Any]]:
        tdx_symbol = to_tdx_http_code(symbol)
        native = await self.client.call(
            "get_gb_info",
            {
                "stock_code": tdx_symbol,
                "date_list": date_list,
                "count": count,
            },
        )
        return [normalize_share_capital_item(tdx_symbol, item) for item in native_items(native)]

    async def get_share_capital_by_date(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        tdx_symbol = to_tdx_http_code(symbol)
        native = await self.client.call(
            "get_gb_info_by_date",
            {
                "stock_code": tdx_symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        return [normalize_share_capital_item(tdx_symbol, item) for item in native_items(native)]

    async def get_dividend_factors(
        self,
        symbol: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict[str, Any]]:
        tdx_symbol = to_tdx_http_code(symbol)
        native = await self.client.call(
            "get_divid_factors",
            {
                "stock_code": tdx_symbol,
                "start_time": start_time or "",
                "end_time": end_time or "",
            },
        )
        return [
            normalize_dividend_factor_item(tdx_symbol, item)
            for item in native_items(native, "Factors")
        ]

    async def get_convertible_bond_info(
        self,
        symbol: str,
        fields: list[str] | None = None,
        native_method: str = "get_kzz_info",
    ) -> list[dict[str, Any]]:
        tdx_symbol = to_tdx_http_code(symbol)
        native = await self.client.call(
            native_method,
            {
                "stock_code": tdx_symbol,
                "field_list": fields or [],
            },
        )
        return [normalize_convertible_bond_item(tdx_symbol, item) for item in native_items(native)]

    async def get_tracking_etfs(self, index_symbol: str) -> list[dict[str, Any]]:
        native = await self.client.call("get_trackzs_etf_info", {"zs_code": index_symbol})
        return [
            normalize_tracking_etf_item(index_symbol, item) for item in native_items(native, "ETFs")
        ]


def _normalize_trading_date(value: Any) -> str:
    text = str(value)
    if len(text) == 8 and text.isdigit():
        return f"{text[0:4]}-{text[4:6]}-{text[6:8]}"
    return text
