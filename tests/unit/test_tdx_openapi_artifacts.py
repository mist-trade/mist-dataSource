import json
from pathlib import Path

from tdx.main import app

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_JSON = ROOT / "docs" / "references" / "tdx-openapi.json"
OPENAPI_SUMMARY = ROOT / "docs" / "references" / "tdx-openapi-summary.md"
MODE_ARTIFACTS = {
    "tdx-legacy": ROOT / "docs" / "references" / "tdx-openapi-legacy.json",
    "tdx-builtin": ROOT
    / "docs"
    / "references"
    / "tdx-openapi-builtin-experimental.json",
    "qmt-off": ROOT / "docs" / "references" / "qmt-openapi-off.json",
    "qmt-builtin": ROOT
    / "docs"
    / "references"
    / "qmt-openapi-builtin-experimental.json",
}


def test_tdx_openapi_json_matches_fastapi_schema() -> None:
    exported = json.loads(OPENAPI_JSON.read_text(encoding="utf-8"))
    current = app.openapi()

    assert exported["openapi"] == current["openapi"]
    assert exported["info"] == current["info"]
    assert exported["paths"] == current["paths"]
    assert exported["components"]["schemas"] == current["components"]["schemas"]
    assert "/v1/finance/financial-data/query" in exported["paths"]
    assert "/v1/reports/data/query" not in exported["paths"]


def test_tdx_openapi_summary_documents_contract_shapes() -> None:
    summary = OPENAPI_SUMMARY.read_text(encoding="utf-8")

    assert "# TDX OpenAPI Summary (legacy)" in summary
    assert "POST /v1/finance/financial-data/query" in summary
    assert "Request Body" in summary
    assert "Responses" in summary
    assert "TdxFinancialDataQueryRequest" in summary
    assert "/v1/reports/data/query" not in summary


def test_mode_specific_openapi_artifacts_document_conditional_routes() -> None:
    schemas = {
        name: json.loads(path.read_text(encoding="utf-8"))
        for name, path in MODE_ARTIFACTS.items()
    }

    assert "/tdx/bridge/health" not in schemas["tdx-legacy"]["paths"]
    assert "/tdx/bridge/health" in schemas["tdx-builtin"]["paths"]
    assert "/tdx/bridge/evidence/{symbol}" in schemas["tdx-builtin"]["paths"]
    assert "/qmt/realtime/health" not in schemas["qmt-off"]["paths"]
    assert "/qmt/realtime/health" in schemas["qmt-builtin"]["paths"]
