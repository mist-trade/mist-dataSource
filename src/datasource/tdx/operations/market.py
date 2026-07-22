import re
from typing import Any

from src.datasource.tdx.errors import TdxNativeError
from src.datasource.tdx.http_client import TdxHttpClient
from src.datasource.tdx.models import TdxBar, TdxSnapshot
from src.datasource.tdx.native import (
    first_native_value,
    native_item_for_symbol,
    native_mapping,
    optional_float,
)
from src.datasource.tdx.normalization import (
    normalize_symbol,
    normalize_tdx_bar_rows,
    normalize_tdx_snapshot,
    to_tdx_http_code,
)

TDX_MARKET_DATA_FIELDS = ["Open", "High", "Low", "Close", "Volume", "Amount"]
TDX_DATE_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


class TdxMarketOperations:
    def __init__(self, client: TdxHttpClient) -> None:
        self.client = client

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
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        params: dict[str, Any] = {
            "stock_list": tdx_symbols,
            "field_list": fields if fields is not None else TDX_MARKET_DATA_FIELDS,
            "period": period,
            "start_time": to_tdx_native_date(start_time),
            "end_time": to_tdx_native_date(end_time),
            "count": count,
        }
        if dividend_type is not None:
            params["dividend_type"] = dividend_type
        if fill_data is not None:
            params["fill_data"] = fill_data

        native = await self.client.call("get_market_data", params)
        raise_for_native_error(native)

        bars: list[TdxBar] = []
        for symbol in tdx_symbols:
            bars.extend(normalize_tdx_bar_rows(symbol, period, native))
        return bars

    async def collect_recent_bars(
        self,
        symbols: list[str],
        period: str,
        count: int,
    ) -> list[TdxBar]:
        return await self.get_bars(
            symbols,
            period=period,
            start_time=None,
            end_time=None,
            count=count,
        )

    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        snapshots: list[TdxSnapshot] = []
        for symbol in symbols:
            tdx_symbol = to_tdx_http_code(symbol)
            native = await self.client.call(
                "get_market_snapshot",
                {
                    "stock_code": tdx_symbol,
                    "field_list": fields or [],
                },
            )
            snapshots.append(normalize_tdx_snapshot(tdx_symbol, native))
        return snapshots

    async def get_price_volume(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        tdx_symbols = [to_tdx_http_code(symbol) for symbol in symbols]
        native = await self.client.call(
            "get_pricevol",
            {
                "stock_list": tdx_symbols,
                "field_list": fields or [],
            },
        )
        return [_normalize_price_volume_item(symbol, native) for symbol in tdx_symbols]


def to_tdx_native_date(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return text
    if re.fullmatch(r"\d{8}", text):
        return text
    match = TDX_DATE_PREFIX_RE.match(text)
    if match:
        return "".join(match.groups())
    return text


def raise_for_native_error(native: Any) -> None:
    native_mapping_value = native_mapping(native)
    if native_mapping_value is None:
        return
    error_id = native_mapping_value.get("ErrorId")
    if error_id is not None and str(error_id) != "0":
        raise TdxNativeError(native_mapping_value)


def _normalize_price_volume_item(symbol: str, native: Any) -> dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol)
    native_item = native_item_for_symbol(native, normalized_symbol)
    native_dict = native_mapping(native_item) or {}
    return {
        "symbol": normalized_symbol,
        "price": optional_float(first_native_value(native_dict, "price", "now", "Now", "last")),
        "volume": optional_float(first_native_value(native_dict, "volume", "Volume")),
        "amount": optional_float(first_native_value(native_dict, "amount", "Amount")),
        "provider": "tdx",
        "raw": native_item,
    }
