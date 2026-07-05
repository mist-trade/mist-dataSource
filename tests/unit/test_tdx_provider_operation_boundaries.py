"""Boundary tests for the TDX provider facade and internal operations."""

from __future__ import annotations

from pathlib import Path

from src.datasource.tdx.operations.finance import TdxFinanceOperations
from src.datasource.tdx.operations.formula import TdxFormulaOperations
from src.datasource.tdx.operations.market import TdxMarketOperations
from src.datasource.tdx.operations.reference import TdxReferenceOperations
from src.datasource.tdx.operations.sector import TdxSectorOperations
from src.datasource.tdx_provider import TdxDatasourceProvider
from tests.unit.test_tdx_provider import FakeTdxHttpClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_provider_facade_composes_domain_operation_modules() -> None:
    provider = TdxDatasourceProvider(FakeTdxHttpClient({}))

    assert isinstance(provider._market, TdxMarketOperations)
    assert isinstance(provider._reference, TdxReferenceOperations)
    assert isinstance(provider._finance, TdxFinanceOperations)
    assert isinstance(provider._sector, TdxSectorOperations)
    assert isinstance(provider._formula, TdxFormulaOperations)


def test_normalized_routes_and_collectors_depend_on_provider_facade_only() -> None:
    checked_files = [
        PROJECT_ROOT / "tdx" / "routes" / "v1" / "product.py",
        PROJECT_ROOT / "src" / "datasource" / "tdx_legacy" / "collector.py",
    ]

    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in checked_files
        if "src.datasource.tdx.operations" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
