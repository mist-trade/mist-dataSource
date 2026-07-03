"""Direct tests for TDX formula normalizers and errors."""

from __future__ import annotations

from src.datasource.tdx.normalizers.formula import (
    TdxFormulaRequestLimitError,
    TdxFormulaTimeoutError,
    formula_batch_method,
    formula_execution_method,
    normalize_formula_batch_result,
    normalize_formula_data_item,
    normalize_formula_data_items,
    normalize_formula_execution_result,
    normalize_formula_info_item,
    normalize_formula_metadata_item,
    normalize_formula_operation_result,
)


def test_normalize_formula_data_items_accepts_symbol_mapping() -> None:
    items = normalize_formula_data_items({"Value": {"688318.SH": [{"Close": "144.4"}]}})

    assert items == [
        {
            "symbol": "688318.SH",
            "rows": [{"Close": "144.4"}],
            "provider": "tdx",
            "raw": [{"Close": "144.4"}],
        }
    ]
    assert normalize_formula_data_item({"Value": []}) == {
        "symbol": None,
        "rows": [],
        "provider": "tdx",
        "raw": [],
    }


def test_normalize_formula_operation_metadata_and_info_results() -> None:
    assert normalize_formula_operation_result({"Value": {"Result": "OK"}}) == {
        "ok": True,
        "message": "OK",
        "provider": "tdx",
        "raw": {"Result": "OK"},
    }
    metadata = normalize_formula_metadata_item(
        {"FormulaCode": "ZB001", "FormulaName": "指标", "Type": "1", "IsSystem": "1"}
    )
    assert metadata["code"] == "ZB001"
    assert metadata["type"] == 1
    assert metadata["isSystem"] is True

    info = normalize_formula_info_item(
        {
            "Value": {
                "FormulaCode": "ZB001",
                "FormulaName": "指标",
                "Params": ["N"],
                "Lines": ["A:1;"],
            }
        }
    )
    assert info["params"] == ["N"]
    assert info["lines"] == ["A:1;"]


def test_normalize_formula_execution_and_batch_results() -> None:
    assert normalize_formula_execution_result("zb", "MA", {"Value": [1, 2]}) == {
        "kind": "zb",
        "formulaName": "MA",
        "values": [1, 2],
        "provider": "tdx",
        "raw": [1, 2],
    }
    assert normalize_formula_batch_result(
        "xg",
        "SELECT",
        {"Value": [{"Code": "600519.SH"}]},
    )["items"] == [{"Code": "600519.SH"}]


def test_formula_method_mappings_are_stable() -> None:
    assert formula_execution_method("zb") == "formula_zb"
    assert formula_execution_method("xg") == "formula_xg"
    assert formula_execution_method("exp") == "formula_exp"
    assert formula_batch_method("zb") == "formula_process_mul_zb"
    assert formula_batch_method("xg") == "formula_process_mul_xg"
    assert formula_batch_method("exp") == "formula_process_mul_exp"


def test_formula_errors_expose_stable_datasource_error_shape() -> None:
    limit_error = TdxFormulaRequestLimitError(limit="stocks", observed=201, maximum=200)
    timeout_error = TdxFormulaTimeoutError(method="formula_zb", timeout_ms=100)

    assert limit_error.code == "FORMULA_REQUEST_LIMIT_EXCEEDED"
    assert limit_error.retryable is False
    assert limit_error.details == {
        "limit": "stocks",
        "observed": 201,
        "maximum": 200,
    }
    assert timeout_error.code == "FORMULA_TIMEOUT"
    assert timeout_error.retryable is True
    assert timeout_error.details == {"method": "formula_zb", "timeoutMs": 100}
