import asyncio
from typing import Any

from src.datasource.tdx.http_client import TdxHttpClient
from src.datasource.tdx.native import native_items
from src.datasource.tdx.normalizers.formula import (
    TdxFormulaTimeoutError,
    effective_formula_timeout_ms,
    formula_batch_method,
    formula_execution_method,
    normalize_formula_batch_result,
    normalize_formula_data_item,
    normalize_formula_data_items,
    normalize_formula_execution_result,
    normalize_formula_info_item,
    normalize_formula_metadata_item,
    normalize_formula_operation_result,
    payload_formula_timeout_ms,
)


class TdxFormulaOperations:
    def __init__(self, client: TdxHttpClient) -> None:
        self.client = client

    async def format_formula_data(
        self,
        data: dict[str, Any],
        timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        native = await self.call_formula_method(
            "formula_format_data",
            {"data_dict": data},
            timeout_ms=timeout_ms,
        )
        return normalize_formula_data_items(native)

    async def set_formula_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        native = await self.call_formula_method(
            "formula_set_data",
            {
                "stock_code": payload.get("stockCode", ""),
                "stock_period": payload.get("stockPeriod", "1d"),
                "stock_data": payload.get("stockData", []),
                "count": payload.get("count", -1),
                "dividend_type": payload.get("dividendType", 0),
            },
            timeout_ms=payload_formula_timeout_ms(payload),
        )
        return normalize_formula_operation_result(native)

    async def set_formula_data_info(self, payload: dict[str, Any]) -> dict[str, Any]:
        native = await self.call_formula_method(
            "formula_set_data_info",
            {
                "stock_code": payload.get("stockCode", ""),
                "stock_period": payload.get("stockPeriod", "1d"),
                "start_time": payload.get("startTime", ""),
                "end_time": payload.get("endTime", ""),
                "count": payload.get("count", -1),
                "dividend_type": payload.get("dividendType", 0),
            },
            timeout_ms=payload_formula_timeout_ms(payload),
        )
        return normalize_formula_operation_result(native)

    async def get_formula_data(self, timeout_ms: int | None = None) -> dict[str, Any]:
        native = await self.call_formula_method("formula_get_data", {}, timeout_ms=timeout_ms)
        return normalize_formula_data_item(native)

    async def get_formula_list(
        self,
        formula_type: int = 0,
        timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        native = await self.call_formula_method(
            "formula_get_all",
            {"formula_type": formula_type},
            timeout_ms=timeout_ms,
        )
        return [normalize_formula_metadata_item(item) for item in native_items(native)]

    async def get_formula_info(
        self,
        formula_type: int,
        formula_code: str,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        native = await self.call_formula_method(
            "formula_get_info",
            {
                "formula_type": formula_type,
                "formula_code": formula_code,
            },
            timeout_ms=timeout_ms,
        )
        return normalize_formula_info_item(native)

    async def execute_formula(
        self,
        kind: str,
        formula_name: str,
        formula_arg: str,
        xsflag: int | None,
        timeout_ms: int | None = None,
    ) -> dict[str, Any]:
        method = formula_execution_method(kind)
        params: dict[str, Any] = {
            "formula_name": formula_name,
            "formula_arg": formula_arg,
        }
        if kind == "zb" and xsflag is not None:
            params["xsflag"] = xsflag
        native = await self.call_formula_method(method, params, timeout_ms=timeout_ms)
        return normalize_formula_execution_result(kind, formula_name, native)

    async def execute_formula_batch(
        self,
        kind: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        method = formula_batch_method(kind)
        native = await self.call_formula_method(
            method,
            {
                "formula_name": payload.get("formulaName", ""),
                "formula_arg": payload.get("formulaArg", ""),
                "return_count": payload.get("returnCount", 1),
                "return_date": payload.get("returnDate", False),
                "stock_list": payload.get("stockList", []),
                "stock_period": payload.get("stockPeriod", "1d"),
                "start_time": payload.get("startTime", ""),
                "end_time": payload.get("endTime", ""),
                "count": payload.get("count", -1),
                "dividend_type": payload.get("dividendType", 0),
            },
            timeout_ms=payload_formula_timeout_ms(payload),
        )
        return normalize_formula_batch_result(kind, payload.get("formulaName", ""), native)

    async def call_formula(
        self,
        name: str,
        args: dict[str, Any] | list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        return await self.client.call(
            name,
            {
                "args": args,
                "context": context or {},
            },
        )

    async def call_formula_method(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout_ms: int | None = None,
    ) -> Any:
        effective_timeout_ms = effective_formula_timeout_ms(timeout_ms)
        try:
            return await asyncio.wait_for(
                self.client.call(method, params),
                timeout=max(effective_timeout_ms, 1) / 1000,
            )
        except TimeoutError as exc:
            raise TdxFormulaTimeoutError(
                method=method,
                timeout_ms=effective_timeout_ms,
            ) from exc
