from typing import Any

from src.core.config import settings
from src.datasource.tdx.errors import (
    TdxMethodForbiddenError as TdxMethodForbiddenError,
    TdxNativeError as TdxNativeError,
    TdxSymbolNotFoundError as TdxSymbolNotFoundError,
)
from src.datasource.tdx.http_client import TdxHttpClient
from src.datasource.tdx.models import TdxBar
from src.datasource.tdx.normalizers.formula import (
    TdxFormulaRequestLimitError as TdxFormulaRequestLimitError,
)
from src.datasource.tdx.normalizers.formula import (
    TdxFormulaTimeoutError as TdxFormulaTimeoutError,
)
from src.datasource.tdx.operations.finance import TdxFinanceOperations
from src.datasource.tdx.operations.formula import TdxFormulaOperations
from src.datasource.tdx.operations.market import TdxMarketOperations
from src.datasource.tdx.operations.reference import TdxReferenceOperations
from src.datasource.tdx.operations.sector import TdxSectorOperations

TDX_HEALTH_PROBE_SYMBOL = "600519.SH"

FORBIDDEN_RAW_METHODS: set[str] = {
    "order_stock",
    "cancel_order",
    "send_order",
    "buy_stock",
    "sell_stock",
    "cancel_order_stock",
    "query_order",
    "query_trade",
    "query_capital",
    "query_position",
    "query_account",
    "query_asset",
    "query_deal",
    "get_orders",
    "get_positions",
    "get_capital",
    "get_account_data",
    "get_trade_account",
}

FORBIDDEN_RAW_PREFIXES: tuple[str, ...] = (
    "order_",
    "buy_",
    "sell_",
    "cancel_order",
    "send_order",
    "entrust_",
    "withdraw_",
)

__all__ = [
    "TdxDatasourceProvider",
    "TdxFormulaRequestLimitError",
    "TdxFormulaTimeoutError",
    "TdxMethodForbiddenError",
    "TdxNativeError",
    "TdxSymbolNotFoundError",
]


class TdxDatasourceProvider:
    def __init__(self, client: TdxHttpClient | None = None) -> None:
        self.client = client or TdxHttpClient(settings.tdx.http_url)
        self._market = TdxMarketOperations(self.client)
        self._reference = TdxReferenceOperations(self.client)
        self._finance = TdxFinanceOperations(self.client)
        self._sector = TdxSectorOperations(self.client)
        self._formula = TdxFormulaOperations(self.client)

    async def get_bars(
        self,
        symbols: list[str],
        *,
        period: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
        fields: list[str] | None = None,
        dividend_type: str | None = None,
        fill_data: bool | None = None,
    ) -> list[TdxBar]:
        return await self._market.get_bars(
            symbols,
            period=period,
            start_time=start_time,
            end_time=end_time,
            count=count,
            fields=fields,
            dividend_type=dividend_type,
            fill_data=fill_data,
        )

    async def collect_recent_bars(
        self,
        symbols: list[str],
        period: str,
        count: int,
    ) -> list[TdxBar]:
        return await self._market.collect_recent_bars(symbols, period, count)

    async def get_price_volume(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._market.get_price_volume(symbols, fields)

    async def get_trading_dates(
        self,
        market: str,
        start_time: str | None = None,
        end_time: str | None = None,
        count: int | None = None,
    ) -> list[str]:
        return await self._reference.get_trading_dates(
            market,
            start_time=start_time,
            end_time=end_time,
            count=count,
        )

    async def get_securities(self, market: str = "5") -> list[dict[str, Any]]:
        return await self._reference.get_securities(market)

    async def get_security_info(self, symbols: list[str]) -> list[dict[str, Any]]:
        return await self._reference.get_security_info(symbols)

    async def get_security_relations(self, symbol: str) -> list[dict[str, Any]]:
        return await self._reference.get_security_relations(symbol)

    async def get_ipo_info(self, ipo_type: int = 0, ipo_date: int = 0) -> list[dict[str, Any]]:
        return await self._reference.get_ipo_info(ipo_type=ipo_type, ipo_date=ipo_date)

    async def get_share_capital(
        self,
        symbol: str,
        date_list: list[str],
        count: int,
    ) -> list[dict[str, Any]]:
        return await self._reference.get_share_capital(symbol, date_list, count)

    async def get_share_capital_by_date(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        return await self._reference.get_share_capital_by_date(symbol, start_date, end_date)

    async def get_dividend_factors(
        self,
        symbol: str,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._reference.get_dividend_factors(symbol, start_time, end_time)

    async def get_convertible_bond_info(
        self,
        symbol: str,
        fields: list[str] | None = None,
        native_method: str = "get_kzz_info",
    ) -> list[dict[str, Any]]:
        return await self._reference.get_convertible_bond_info(symbol, fields, native_method)

    async def get_tracking_etfs(self, index_symbol: str) -> list[dict[str, Any]]:
        return await self._reference.get_tracking_etfs(index_symbol)

    async def get_financial_data(
        self,
        symbols: list[str],
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
        report_type: str = "report_time",
    ) -> list[dict[str, Any]]:
        return await self._finance.get_financial_data(
            symbols,
            fields,
            start_time,
            end_time,
            report_type,
        )

    async def get_financial_data_by_date(
        self,
        symbols: list[str],
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._finance.get_financial_data_by_date(symbols, fields, year, mmdd)

    async def get_single_finance_values(
        self,
        symbols: list[str],
        fields: list[str],
    ) -> list[dict[str, Any]]:
        return await self._finance.get_single_finance_values(symbols, fields)

    async def get_stock_trade_aggregate(
        self,
        symbols: list[str],
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        return await self._finance.get_stock_trade_aggregate(
            symbols,
            fields,
            start_time,
            end_time,
        )

    async def get_stock_trade_aggregate_by_date(
        self,
        symbols: list[str],
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._finance.get_stock_trade_aggregate_by_date(
            symbols,
            fields,
            year,
            mmdd,
        )

    async def get_sector_trade_aggregate(
        self,
        sector_codes: list[str],
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        return await self._finance.get_sector_trade_aggregate(
            sector_codes,
            fields,
            start_time,
            end_time,
        )

    async def get_sector_trade_aggregate_by_date(
        self,
        sector_codes: list[str],
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._finance.get_sector_trade_aggregate_by_date(
            sector_codes,
            fields,
            year,
            mmdd,
        )

    async def get_market_trade_aggregate(
        self,
        fields: list[str],
        start_time: str = "",
        end_time: str = "",
    ) -> list[dict[str, Any]]:
        return await self._finance.get_market_trade_aggregate(fields, start_time, end_time)

    async def get_market_trade_aggregate_by_date(
        self,
        fields: list[str],
        year: int = 0,
        mmdd: int = 0,
    ) -> list[dict[str, Any]]:
        return await self._finance.get_market_trade_aggregate_by_date(fields, year, mmdd)

    async def format_formula_data(
        self,
        data: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        return await self._formula.format_formula_data(data, timeout_ms)

    async def set_formula_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._formula.set_formula_data(payload)

    async def set_formula_data_info(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._formula.set_formula_data_info(payload)

    async def get_formula_data(self, timeout_ms: int | None = None) -> dict[str, Any]:
        return await self._formula.get_formula_data(timeout_ms)

    async def get_formula_list(
        self,
        formula_type: int = 0,
        timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        return await self._formula.get_formula_list(formula_type, timeout_ms)

    async def get_formula_info(
        self,
        formula_type: int,
        formula_code: str,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        return await self._formula.get_formula_info(formula_type, formula_code, timeout_ms)

    async def execute_formula(
        self,
        kind: str,
        formula_name: str,
        formula_arg: str,
        xsflag: int | None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        return await self._formula.execute_formula(
            kind,
            formula_name,
            formula_arg,
            xsflag,
            timeout_ms,
        )

    async def execute_formula_batch(
        self,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._formula.execute_formula_batch(kind, payload)

    async def _call_formula_method(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_ms: int | None = None,
    ) -> Any:
        return await self._formula.call_formula_method(
            method,
            params,
            timeout_ms=timeout_ms,
        )

    async def raw_call(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> Any:
        normalized_method = (method or "").strip().lower()
        if (
            normalized_method in FORBIDDEN_RAW_METHODS
            or any(normalized_method.startswith(prefix) for prefix in FORBIDDEN_RAW_PREFIXES)
        ):
            raise TdxMethodForbiddenError(method=method)
        return await self.client.call(method, params)

    async def get_sector_list(self, list_type: int = 0) -> list[dict[str, Any]]:
        return await self._sector.get_sector_list(list_type)

    async def get_sector_members(self, sector: str) -> list[str]:
        return await self._sector.get_sector_members(sector)

    async def call_formula(
        self,
        name: str,
        args: dict[str, Any] | list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        return await self._formula.call_formula(name, args, context)

    async def health(self) -> dict[str, Any]:
        try:
            await self.client.call(
                "get_market_snapshot",
                {
                    "stock_code": TDX_HEALTH_PROBE_SYMBOL,
                    "field_list": [],
                },
            )
        except Exception as exc:
            return {
                "tdxHttpReachable": False,
                "lastError": str(exc),
            }

        return {
            "tdxHttpReachable": True,
            "lastError": None,
        }

    async def aclose(self) -> None:
        await self.client.aclose()
