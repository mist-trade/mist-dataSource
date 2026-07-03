from typing import Any

from src.core.config import settings
from src.datasource.tdx.native import (
    as_sequence,
    first_native_value,
    native_items,
    native_mapping,
    native_record,
    native_sequence,
    optional_bool,
    optional_int,
    unwrap_tdx_value,
)
from src.datasource.tdx_models import TdxFormulaOperationResult
from src.datasource.tdx_normalization import normalize_symbol


class TdxFormulaRequestLimitError(Exception):
    def __init__(
        self,
        *,
        limit: str,
        observed: int,
        maximum: int,
    ) -> None:
        super().__init__(f"Formula request exceeds {limit} limit")
        self.code = "FORMULA_REQUEST_LIMIT_EXCEEDED"
        self.message = f"Formula request exceeds {limit} limit"
        self.retryable = False
        self.details = {
            "limit": limit,
            "observed": observed,
            "maximum": maximum,
        }


class TdxFormulaTimeoutError(Exception):
    def __init__(self, *, method: str, timeout_ms: int) -> None:
        super().__init__(f"Formula method {method} timed out after {timeout_ms} ms")
        self.code = "FORMULA_TIMEOUT"
        self.message = f"Formula method {method} timed out after {timeout_ms} ms"
        self.retryable = True
        self.details = {
            "method": method,
            "timeoutMs": timeout_ms,
        }


def effective_formula_timeout_ms(timeout_ms: int | None = None) -> int:
    if timeout_ms is None:
        return settings.tdx.formula_timeout_ms
    return int(timeout_ms)


def payload_formula_timeout_ms(payload: dict[str, Any]) -> int:
    timeout_ms = payload.get("timeoutMs")
    return effective_formula_timeout_ms(int(timeout_ms) if timeout_ms is not None else None)


def normalize_formula_data_items(native: Any) -> list[dict[str, Any]]:
    values = unwrap_tdx_value(native)
    values_mapping = native_mapping(values)
    if values_mapping is not None:
        return [
            {
                "symbol": normalize_symbol(str(symbol)),
                "rows": as_sequence(rows),
                "provider": "tdx",
                "raw": rows,
            }
            for symbol, rows in values_mapping.items()
        ]
    if isinstance(values, list | tuple):
        values_sequence = native_sequence(values)
        return [
            {
                "symbol": None,
                "rows": values_sequence,
                "provider": "tdx",
                "raw": values_sequence,
            }
        ]
    return []


def normalize_formula_data_item(native: Any) -> dict[str, Any]:
    items = normalize_formula_data_items(native)
    if items:
        return items[0]
    values = unwrap_tdx_value(native)
    return {
        "symbol": None,
        "rows": as_sequence(values),
        "provider": "tdx",
        "raw": values,
    }


def normalize_formula_operation_result(native: Any) -> dict[str, Any]:
    values = unwrap_tdx_value(native)
    values_mapping = native_mapping(values)
    if values_mapping is not None:
        message = first_native_value(values_mapping, "Result", "message", "Message")
        result = TdxFormulaOperationResult(
            ok=True,
            message=str(message) if message is not None else "OK",
            raw=values_mapping,
        )
        return result.model_dump(by_alias=True)
    if isinstance(values, bool):
        result = TdxFormulaOperationResult(
            ok=values,
            message="OK" if values else "FAILED",
            raw=values,
        )
        return result.model_dump(by_alias=True)
    result = TdxFormulaOperationResult(ok=True, message=str(values), raw=values)
    return result.model_dump(by_alias=True)


def normalize_formula_metadata_item(item: Any) -> dict[str, Any]:
    native = native_record(item)
    code = first_native_value(native, "FormulaCode", "Code", "code")
    name = first_native_value(native, "FormulaName", "Name", "name")
    formula_type = first_native_value(native, "Type", "formulaType", "type")
    is_system = first_native_value(native, "IsSystem", "isSystem")
    return {
        "code": str(code) if code is not None else "",
        "name": str(name) if name is not None else None,
        "type": optional_int(formula_type),
        "isSystem": optional_bool(is_system),
        "provider": "tdx",
        "raw": item,
    }


def normalize_formula_info_item(native: Any) -> dict[str, Any]:
    values = unwrap_tdx_value(native)
    item = native_record(values)
    metadata = normalize_formula_metadata_item(item)
    metadata["params"] = as_sequence(first_native_value(item, "Params", "params"))
    metadata["lines"] = as_sequence(first_native_value(item, "Lines", "lines"))
    return metadata


def normalize_formula_execution_result(
    kind: str,
    formula_name: str,
    native: Any,
) -> dict[str, Any]:
    values = unwrap_tdx_value(native)
    return {
        "kind": kind,
        "formulaName": formula_name,
        "values": values,
        "provider": "tdx",
        "raw": values,
    }


def normalize_formula_batch_result(
    kind: str,
    formula_name: str,
    native: Any,
) -> dict[str, Any]:
    values = unwrap_tdx_value(native)
    return {
        "kind": kind,
        "formulaName": formula_name,
        "items": native_items(values),
        "provider": "tdx",
        "raw": values,
    }


def formula_execution_method(kind: str) -> str:
    methods = {
        "zb": "formula_zb",
        "xg": "formula_xg",
        "exp": "formula_exp",
    }
    return methods[kind]


def formula_batch_method(kind: str) -> str:
    methods = {
        "zb": "formula_process_mul_zb",
        "xg": "formula_process_mul_xg",
        "exp": "formula_process_mul_exp",
    }
    return methods[kind]
