"""TDX route registration contracts after builtin realtime convergence."""

from pathlib import Path

from fastapi import FastAPI

from tdx.main import app, create_tdx_app

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _paths(target: FastAPI = app) -> set[str]:
    paths: set[str] = set()
    for app_route in target.routes:
        path = getattr(app_route, "path", None)
        if path is not None:
            paths.add(str(path))
            continue
        original_router = getattr(app_route, "original_router", None)
        include_context = getattr(app_route, "include_context", None)
        prefix = str(getattr(include_context, "prefix", ""))
        for route in getattr(original_router, "routes", []):
            paths.add(prefix + str(getattr(route, "path", "")))
    return paths


def test_tdx_mounts_only_v1_and_builtin_realtime_surfaces() -> None:
    paths = _paths()
    assert "/v1/bars/query" in paths
    assert "/v1/snapshots/query" not in paths
    assert "/tdx/bridge/owner" in paths
    assert "/tdx/bridge/health" in paths
    assert "/ws/realtime/tdx/{client_id}" in paths


def test_tdx_off_keeps_product_apis_and_omits_realtime_surfaces() -> None:
    off_app = create_tdx_app(realtime_mode="off")
    paths = _paths(off_app)

    assert "/v1/bars/query" in paths
    assert "/v1/snapshots/query" not in paths
    assert "/tdx/bridge/owner" not in paths
    assert "/tdx/bridge/health" not in paths
    assert "/ws/realtime/tdx/{client_id}" not in paths


def test_tdx_legacy_routes_are_removed() -> None:
    paths = _paths()
    assert not any(path.startswith("/api/tdx/") for path in paths)
    assert "/ws/quote/{client_id}" not in paths


def test_retired_tdx_config_and_websocket_models_stay_removed() -> None:
    assert not (PROJECT_ROOT / "tdx" / "config.py").exists()
    models = (PROJECT_ROOT / "src" / "datasource" / "tdx" / "models.py").read_text()
    protocol = (PROJECT_ROOT / "src" / "ws" / "protocol.py").read_text()
    assert "class TdxWsMessage" not in models
    assert "def ws_quote" not in protocol
