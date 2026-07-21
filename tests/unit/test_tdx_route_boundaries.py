"""TDX route registration contracts after builtin realtime convergence."""

from tdx.main import app


def _paths() -> set[str]:
    paths: set[str] = set()
    for app_route in app.routes:
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
    assert "/providers" in paths
    assert "/v1/bars/query" in paths
    assert "/v1/snapshots/query" in paths
    assert "/tdx/bridge/owner" in paths
    assert "/tdx/bridge/health" in paths
    assert "/ws/tdx-experimental/{client_id}" in paths


def test_tdx_legacy_routes_are_removed() -> None:
    paths = _paths()
    assert not any(path.startswith("/api/tdx/") for path in paths)
    assert "/ws/quote/{client_id}" not in paths
