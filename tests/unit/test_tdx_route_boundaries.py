"""TDX route registration and package boundary contracts."""

from __future__ import annotations

from dataclasses import dataclass

from tdx.main import app


@dataclass(frozen=True)
class RegisteredRoute:
    path: str
    methods: frozenset[str]
    module: str


def _registered_routes() -> list[RegisteredRoute]:
    routes: list[RegisteredRoute] = []

    for app_route in app.routes:
        original_router = getattr(app_route, "original_router", None)
        include_context = getattr(app_route, "include_context", None)
        if original_router is None or include_context is None:
            continue

        prefix = str(getattr(include_context, "prefix", ""))
        for route in getattr(original_router, "routes", []):
            endpoint = getattr(route, "endpoint", None)
            module = str(getattr(endpoint, "__module__", ""))
            path = f"{prefix}{getattr(route, 'path', '')}"
            methods = getattr(route, "methods", None) or set()
            routes.append(
                RegisteredRoute(
                    path=path,
                    methods=frozenset(str(method) for method in methods),
                    module=module,
                )
            )

    return routes


def _route_by_path(path: str) -> RegisteredRoute:
    routes = {route.path: route for route in _registered_routes()}
    return routes[path]


def test_tdx_route_contract_keeps_legacy_normalized_and_websocket_paths() -> None:
    registered_paths = {route.path for route in _registered_routes()}

    assert {
        "/api/tdx/market-data",
        "/api/tdx/market-snapshot",
        "/api/tdx/stock-list",
        "/api/tdx/financial-data",
        "/api/tdx/bkjy-value",
        "/api/tdx/sector-list",
        "/api/tdx/kzz-info",
        "/api/tdx/exec-to-tdx",
        "/providers",
        "/v1/bars/query",
        "/v1/snapshots/query",
        "/v1/raw/tdx/call",
        "/v1/formulas/zb/execute",
        "/ws/quote/{client_id}",
    } <= registered_paths


def test_tdx_route_contract_keeps_representative_http_methods() -> None:
    assert _route_by_path("/api/tdx/market-data").methods == frozenset({"GET"})
    assert _route_by_path("/api/tdx/exec-to-tdx").methods == frozenset({"POST"})
    assert _route_by_path("/v1/bars/query").methods == frozenset({"POST"})
    assert _route_by_path("/v1/raw/tdx/call").methods == frozenset({"POST"})
    assert _route_by_path("/ws/quote/{client_id}").methods == frozenset()


def test_tdx_route_packages_separate_legacy_v1_and_websocket_boundaries() -> None:
    routes = _registered_routes()
    legacy_modules = {route.module for route in routes if route.path.startswith("/api/tdx/")}
    normalized_modules = {
        route.module
        for route in routes
        if route.path == "/providers" or route.path.startswith("/v1/")
    }
    websocket_modules = {route.module for route in routes if route.path.startswith("/ws/")}

    assert legacy_modules
    assert normalized_modules
    assert websocket_modules == {"tdx.routes.ws"}
    assert all(module.startswith("tdx.routes.legacy.") for module in legacy_modules)
    assert all(module.startswith("tdx.routes.v1") for module in normalized_modules)


def test_tdx_websocket_route_stays_outside_rest_route_packages() -> None:
    websocket_route = _route_by_path("/ws/quote/{client_id}")

    assert websocket_route.module == "tdx.routes.ws"


def test_registered_route_helper_uses_included_router_shape() -> None:
    # Keep this helper honest across FastAPI versions that expose included
    # routers lazily instead of flattening APIRoute instances into app.routes.
    assert all(isinstance(route.path, str) for route in _registered_routes())
    assert all(isinstance(route.methods, frozenset) for route in _registered_routes())
    assert all(isinstance(route.module, str) for route in _registered_routes())
