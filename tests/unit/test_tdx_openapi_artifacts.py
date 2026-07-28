import json
from pathlib import Path

from tdx.main import app

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_JSON = ROOT / "docs" / "references" / "tdx-openapi.json"
OPENAPI_SUMMARY = ROOT / "docs" / "references" / "tdx-openapi-summary.md"
MODE_ARTIFACTS = {
    "tdx-builtin": ROOT / "docs" / "references" / "tdx-openapi-builtin.json",
    "qmt-off": ROOT / "docs" / "references" / "qmt-openapi-off.json",
    "qmt-builtin": ROOT / "docs" / "references" / "qmt-openapi-builtin.json",
}


def test_tdx_openapi_json_matches_fastapi_schema() -> None:
    exported = json.loads(OPENAPI_JSON.read_text(encoding="utf-8"))
    current = app.openapi()

    assert exported["openapi"] == current["openapi"]
    assert exported["info"] == current["info"]
    assert exported["paths"] == current["paths"]
    assert exported["components"]["schemas"] == current["components"]["schemas"]
    assert "/v1/finance/financial-data/query" in exported["paths"]
    assert "/v1/snapshots/query" not in exported["paths"]
    assert "TdxSnapshotQueryRequest" not in exported["components"]["schemas"]
    assert "/v1/reports/data/query" not in exported["paths"]


def test_tdx_openapi_summary_documents_contract_shapes() -> None:
    summary = OPENAPI_SUMMARY.read_text(encoding="utf-8")

    assert "# TDX OpenAPI Summary (builtin)" in summary
    assert "POST /v1/finance/financial-data/query" in summary
    assert "Request Body" in summary
    assert "Responses" in summary
    assert "TdxFinancialDataQueryRequest" in summary
    assert "/v1/snapshots/query" not in summary
    assert "TdxSnapshotQueryRequest" not in summary
    assert "/v1/reports/data/query" not in summary


def test_mode_specific_openapi_artifacts_document_conditional_routes() -> None:
    schemas = {
        name: json.loads(path.read_text(encoding="utf-8")) for name, path in MODE_ARTIFACTS.items()
    }

    assert "/tdx/bridge/health" in schemas["tdx-builtin"]["paths"]
    assert "/tdx/bridge/evidence/{symbol}" in schemas["tdx-builtin"]["paths"]
    assert "/v1/snapshots/query" not in schemas["tdx-builtin"]["paths"]
    assert "/qmt/realtime/health" not in schemas["qmt-off"]["paths"]
    assert "/qmt/realtime/health" in schemas["qmt-builtin"]["paths"]


def test_mode_specific_health_openapi_exposes_normalized_bridge_contract() -> None:
    schemas = {
        name: json.loads(path.read_text(encoding="utf-8")) for name, path in MODE_ARTIFACTS.items()
    }

    for name, schema in schemas.items():
        root_response = schema["paths"]["/health"]["get"]["responses"]["200"]
        root_ref = root_response["content"]["application/json"]["schema"]["$ref"]
        root = schema["components"]["schemas"][root_ref.rsplit("/", 1)[-1]]
        root_properties = root["properties"]
        assert "bridge" in root_properties, name
        assert "tdxRealtimeBridgeReady" not in root_properties, name
        assert "collectorReady" not in root_properties, name
        assert "datasourceBuildId" not in root_properties, name

        bridge_ref = root_properties["bridge"]["$ref"]
        bridge = schema["components"]["schemas"][bridge_ref.rsplit("/", 1)[-1]]
        assert {
            "ready",
            "ownerId",
            "ownerGeneration",
            "bridgeBuildId",
        }.issubset(bridge["properties"]), name
        assert "generation" not in bridge["properties"], name

    for name, path in (
        ("tdx-builtin", "/tdx/bridge/health"),
        ("qmt-builtin", "/qmt/bridge/health"),
    ):
        schema = schemas[name]
        response = schema["paths"][path]["get"]["responses"]["200"]
        bridge_ref = response["content"]["application/json"]["schema"]["$ref"]
        bridge = schema["components"]["schemas"][bridge_ref.rsplit("/", 1)[-1]]
        assert "ready" in bridge["properties"]
        assert "bridge" not in bridge["properties"]
