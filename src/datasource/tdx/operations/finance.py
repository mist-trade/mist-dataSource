from typing import Any

from src.datasource.tdx.http_client import TdxHttpClient
from src.datasource.tdx.market_normalization import to_tdx_http_code
from src.datasource.tdx.normalizers.finance import (
    normalize_financial_data_items,
    normalize_single_finance_value_items,
    normalize_trade_aggregate_items,
)


class TdxFinanceOperations:
    def __init__(self, client: TdxHttpClient) -> None:
        self.client = client

    async def get_financial_data(
        self,
        symbols: list[str],
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
        report_type: str = "report_time",
    ) -> list[dict[str, Any]]:
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        native = await self.client.call(
            "get_financial_data",
            {
                "stock_list": tdx_symbols,
                "field_list": fields,
                "start_time": start_time,
                "end_time": end_time,
                "report_type": report_type,
            },
        )
        return normalize_financial_data_items(tdx_symbols, fields, native)

    async def get_financial_data_by_date(
        self,
        symbols: list[str],
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        native = await self.client.call(
            "get_financial_data_by_date",
            {
                "stock_list": tdx_symbols,
                "field_list": fields,
                "year": year,
                "mmdd": mmdd,
            },
        )
        return normalize_financial_data_items(tdx_symbols, fields, native)

    async def get_single_finance_values(
        self,
        symbols: list[str],
        fields: list[str],
    ) -> list[dict[str, Any]]:
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        native = await self.client.call(
            "get_gp_one_data",
            {
                "stock_list": tdx_symbols,
                "table_list": fields,
            },
        )
        return normalize_single_finance_value_items(tdx_symbols, fields, native)

    async def get_stock_trade_aggregate(
        self,
        symbols: list[str],
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        native = await self.client.call(
            "get_gpjy_value",
            {
                "stock_list": tdx_symbols,
                "field_list": fields,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        return normalize_trade_aggregate_items("stock", tdx_symbols, fields, native)

    async def get_stock_trade_aggregate_by_date(
        self,
        symbols: list[str],
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        native = await self.client.call(
            "get_gpjy_value_by_date",
            {
                "stock_list": tdx_symbols,
                "field_list": fields,
                "year": year,
                "mmdd": mmdd,
            },
        )
        return normalize_trade_aggregate_items("stock", tdx_symbols, fields, native)

    async def get_sector_trade_aggregate(
        self,
        sector_codes: list[str],
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        native = await self.client.call(
            "get_bkjy_value",
            {
                "stock_list": sector_codes,
                "field_list": fields,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        return normalize_trade_aggregate_items("sector", sector_codes, fields, native)

    async def get_sector_trade_aggregate_by_date(
        self,
        sector_codes: list[str],
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        native = await self.client.call(
            "get_bkjy_value_by_date",
            {
                "stock_list": sector_codes,
                "field_list": fields,
                "year": year,
                "mmdd": mmdd,
            },
        )
        return normalize_trade_aggregate_items("sector", sector_codes, fields, native)

    async def get_market_trade_aggregate(
        self,
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        native = await self.client.call(
            "get_scjy_value",
            {
                "field_list": fields,
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        return normalize_trade_aggregate_items("market", [None], fields, native)

    async def get_market_trade_aggregate_by_date(
        self,
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        native = await self.client.call(
            "get_scjy_value_by_date",
            {
                "field_list": fields,
                "year": year,
                "mmdd": mmdd,
            },
        )
        return normalize_trade_aggregate_items("market", [None], fields, native)
