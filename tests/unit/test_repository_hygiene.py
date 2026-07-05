"""Repository hygiene checks for local tooling metadata."""

from __future__ import annotations

import ast
import inspect
import os
import stat
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from src.adapter_legacy.mock.tdx_mock import TdxLegacyMockAdapter
from src.adapter_legacy.tdx.client import TdxLegacyAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_gitignore_excludes_local_tool_caches() -> None:
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    ignored_entries = {
        line.strip()
        for line in gitignore.splitlines()
        if line.strip() and not line.strip().startswith("#")
    }

    assert ".uv-cache/" in ignored_entries
    assert ".ruff_cache/" in ignored_entries


def test_conftest_does_not_define_custom_event_loop_fixture() -> None:
    conftest = PROJECT_ROOT / "tests" / "conftest.py"
    tree = ast.parse(conftest.read_text(encoding="utf-8"), filename=str(conftest))
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }

    assert "event_loop" not in function_names


def test_ci_and_precommit_run_pyright() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    precommit = (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert "uv run pyright" in workflow
    assert "id: pyright" in precommit
    assert "uv run pyright" in precommit


def test_precommit_ruff_version_matches_lockfile() -> None:
    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text(encoding="utf-8"))
    ruff_version = next(
        package["version"] for package in lock["package"] if package["name"] == "ruff"
    )
    precommit = (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    assert f"rev: v{ruff_version}" in precommit


def test_p3_datasource_shape_cleanup_contracts() -> None:
    exceptions_source = (PROJECT_ROOT / "src" / "core" / "exceptions.py").read_text(
        encoding="utf-8"
    )
    core_init_source = (PROJECT_ROOT / "src" / "core" / "__init__.py").read_text(encoding="utf-8")
    tdx_client_source = (
        PROJECT_ROOT / "src" / "adapter_legacy" / "tdx" / "client.py"
    ).read_text(encoding="utf-8")
    tdx_legacy_bridge_source = (
        PROJECT_ROOT / "src" / "datasource" / "tdx_legacy" / "bridge.py"
    ).read_text(encoding="utf-8")
    tdx_subscription_source = (
        PROJECT_ROOT / "src" / "datasource" / "tdx_legacy" / "subscription.py"
    ).read_text(encoding="utf-8")

    assert "class ConnectionError" not in exceptions_source
    assert "class ConfigurationError" not in exceptions_source
    assert "ConnectionError" not in core_init_source
    assert "ConfigurationError" not in core_init_source
    assert "print(" not in tdx_client_source
    assert "get_logger" in tdx_client_source
    assert "def _dedupe_stable" not in tdx_legacy_bridge_source
    assert "def _dedupe_normalized" not in tdx_subscription_source


def test_legacy_service_layers_are_removed() -> None:
    assert not list((PROJECT_ROOT / "tdx" / "services").glob("*.py"))
    assert not list((PROJECT_ROOT / "qmt" / "services").glob("*.py"))


def test_tdx_create_sector_signature_matches_mock_adapter() -> None:
    real_signature = inspect.signature(TdxLegacyAdapter.create_sector)
    mock_signature = inspect.signature(TdxLegacyMockAdapter.create_sector)

    assert list(real_signature.parameters) == ["self", "block_code", "block_name"]
    assert list(mock_signature.parameters) == ["self", "block_code", "block_name"]


def test_ci_reports_live_test_collection_without_running_live_sdk() -> None:
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "-m live" in workflow
    assert "--collect-only" in workflow


def test_shell_scripts_use_strict_mode() -> None:
    for relative_path in (
        "scripts/start_all.sh",
        "scripts/stop_all.sh",
        "scripts/health_check.sh",
    ):
        source = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert "set -euo pipefail" in source, relative_path


def test_health_check_exits_nonzero_when_any_instance_is_unhealthy(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_curl = fake_bin / "curl"
    fake_curl.write_text("#!/bin/sh\nexit 22\n", encoding="utf-8")
    fake_curl.chmod(fake_curl.stat().st_mode | stat.S_IXUSR)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}{os.pathsep}{env['PATH']}"

    result = subprocess.run(
        ["bash", str(PROJECT_ROOT / "scripts" / "health_check.sh")],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode != 0
    assert "NOT RESPONDING" in result.stdout


def test_tdx_routes_do_not_import_tdx_main_for_runtime_singletons() -> None:
    route_files = sorted((PROJECT_ROOT / "tdx" / "routes").rglob("*.py"))

    offenders: list[str] = []
    for route_file in route_files:
        if route_file.name == "__init__.py":
            continue
        tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "tdx.main" for alias in node.names
            ):
                offenders.append(str(route_file.relative_to(PROJECT_ROOT)))
            if isinstance(node, ast.ImportFrom) and node.module == "tdx.main":
                offenders.append(str(route_file.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_qmt_routes_do_not_import_qmt_main_for_runtime_singletons() -> None:
    route_files = sorted((PROJECT_ROOT / "qmt" / "routes").rglob("*.py"))

    offenders: list[str] = []
    for route_file in route_files:
        if route_file.name == "__init__.py":
            continue
        tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(
                alias.name == "qmt.main" for alias in node.names
            ):
                offenders.append(str(route_file.relative_to(PROJECT_ROOT)))
            if isinstance(node, ast.ImportFrom) and node.module == "qmt.main":
                offenders.append(str(route_file.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_tdx_routes_document_app_state_dependency_model() -> None:
    docs = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "app.state" in docs
    assert "import tdx.main" not in docs


def test_claude_adapter_pattern_matches_current_base_adapter_contract() -> None:
    docs = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    assert "70+ methods" not in docs
    assert "lifecycle abstract" in docs
    assert "`initialize()`" in docs
    assert "`shutdown()`" in docs


def test_primary_api_docs_use_v1_endpoints_for_tdx_rest_surface() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    claude = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")

    tdx_api_section = readme.split("#### TDX", 1)[1].split("#### QMT", 1)[0]
    tdx_api_table_rows = [line for line in tdx_api_section.splitlines() if line.startswith("|")]
    assert not any("/api/tdx/" in line for line in tdx_api_table_rows)
    for endpoint in (
        "/v1/bars/query",
        "/v1/snapshots/query",
        "/v1/sectors/query",
        "/v1/finance/financial-data/query",
        "/v1/instruments/convertible-bonds/query",
    ):
        assert endpoint in tdx_api_section

    claude_api_table = claude.split("### API Routes", 1)[1].split("### WebSocket Protocol", 1)[0]
    assert "| TDX | `/api/tdx/" not in claude_api_table
    assert "| TDX | `/v1/bars/query`" in claude_api_table
    assert "| TDX | `/v1/finance/financial-data/query`" in claude_api_table


def test_routes_share_adapter_dependency_helpers() -> None:
    route_roots = (PROJECT_ROOT / "tdx" / "routes", PROJECT_ROOT / "qmt" / "routes")
    offenders: list[str] = []

    for route_root in route_roots:
        for route_file in sorted(route_root.rglob("*.py")):
            if route_file.name in {"dependencies.py", "__init__.py"}:
                continue
            tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "_get_adapter":
                    offenders.append(str(route_file.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_rest_routes_use_shared_adapter_error_wrappers() -> None:
    route_roots = (
        PROJECT_ROOT / "tdx" / "routes" / "legacy",
        PROJECT_ROOT / "qmt" / "routes",
    )
    offenders: list[str] = []

    for route_root in route_roots:
        for route_file in sorted(route_root.rglob("*.py")):
            if route_file.name in {"dependencies.py", "__init__.py", "ws.py"}:
                continue
            tree = ast.parse(route_file.read_text(encoding="utf-8"), filename=str(route_file))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ExceptHandler):
                    continue
                if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    offenders.append(str(route_file.relative_to(PROJECT_ROOT)))

    assert offenders == []


def test_adapter_sdk_error_wrapping_is_centralized() -> None:
    allowed_handlers = {
        ("src/adapter_legacy/tdx/client.py", "_heartbeat_loop"),
        ("src/adapter_legacy/tdx/client.py", "initialize"),
        ("src/adapter_legacy/tdx/client.py", "_call_tq"),
    }
    adapter_files = (
        PROJECT_ROOT / "src" / "adapter_legacy" / "tdx" / "client.py",
    )
    offenders: list[tuple[str, str]] = []

    for adapter_file in adapter_files:
        relative_path = str(adapter_file.relative_to(PROJECT_ROOT))
        tree = ast.parse(adapter_file.read_text(encoding="utf-8"), filename=str(adapter_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            for child in ast.walk(node):
                if not isinstance(child, ast.ExceptHandler):
                    continue
                if isinstance(child.type, ast.Name) and child.type.id == "Exception":
                    handler = (relative_path, node.name)
                    if handler not in allowed_handlers:
                        offenders.append(handler)

    assert offenders == []


def test_tdx_provider_uses_shared_native_key_normalization_and_configured_timeouts() -> None:
    provider_source = (PROJECT_ROOT / "src" / "datasource" / "tdx_provider.py").read_text(
        encoding="utf-8"
    )
    formula_normalizer_source = (
        PROJECT_ROOT / "src" / "datasource" / "tdx" / "normalizers" / "formula.py"
    ).read_text(encoding="utf-8")

    assert '.replace("_", "").replace(" ", "").lower()' not in provider_source
    assert "timeout_ms: int = 10000" not in provider_source
    assert 'payload.get("timeoutMs", 10000)' not in formula_normalizer_source
    assert "settings.tdx.formula_timeout_ms" in formula_normalizer_source


def _assert_selected_adapter_methods_are_typed(
    adapter_cls: type, required_methods: tuple[str, ...]
) -> None:
    for method_name in required_methods:
        signature = inspect.signature(getattr(adapter_cls, method_name))
        assert signature.return_annotation is not inspect.Signature.empty, method_name
        assert signature.return_annotation is not Any, method_name
        assert signature.return_annotation not in {dict, list}, method_name
        for parameter_name, parameter in signature.parameters.items():
            if parameter_name == "self":
                continue
            assert parameter.annotation is not inspect.Signature.empty, (
                method_name,
                parameter_name,
            )


def test_tdx_legacy_adapter_selected_provider_methods_are_typed() -> None:
    _assert_selected_adapter_methods_are_typed(
        TdxLegacyAdapter,
        (
            "subscribe_quote",
            "get_market_snapshot",
            "get_gb_info",
            "get_sector_list",
            "get_kzz_info",
            "get_ipo_info",
            "get_trackzs_etf_info",
            "formula_format_data",
        ),
    )


def test_legacy_qmt_mock_adapter_is_removed() -> None:
    assert not (PROJECT_ROOT / "src" / "adapter" / "mock" / "qmt_mock.py").exists()


def test_tdx_legacy_code_uses_explicit_legacy_paths() -> None:
    assert not (PROJECT_ROOT / "src" / "adapter").exists()
    assert not (PROJECT_ROOT / "src" / "datasource" / "tdx_subscription.py").exists()
    assert not (PROJECT_ROOT / "src" / "datasource" / "tdx_legacy_bridge.py").exists()
    assert not (PROJECT_ROOT / "src" / "datasource" / "tdx_legacy_collector.py").exists()

    assert (PROJECT_ROOT / "src" / "adapter_legacy" / "tdx" / "client.py").exists()
    assert (PROJECT_ROOT / "src" / "datasource" / "tdx_legacy" / "subscription.py").exists()
    assert (PROJECT_ROOT / "src" / "datasource" / "tdx_legacy" / "bridge.py").exists()
    assert (PROJECT_ROOT / "src" / "datasource" / "tdx_legacy" / "collector.py").exists()


def test_tdx_v1_provider_surface_does_not_import_legacy_runtime() -> None:
    v1_files = [
        PROJECT_ROOT / "src" / "datasource" / "tdx_provider.py",
        PROJECT_ROOT / "src" / "datasource" / "tdx_http_client.py",
        PROJECT_ROOT / "src" / "datasource" / "tdx_models.py",
        PROJECT_ROOT / "src" / "datasource" / "tdx_normalization.py",
        *sorted((PROJECT_ROOT / "src" / "datasource" / "tdx" / "operations").glob("*.py")),
        *sorted((PROJECT_ROOT / "src" / "datasource" / "tdx" / "normalizers").glob("*.py")),
        PROJECT_ROOT / "tdx" / "routes" / "v1" / "product.py",
    ]

    offenders: list[str] = []
    for source_file in v1_files:
        source = source_file.read_text(encoding="utf-8")
        if "src.adapter_legacy" in source or "src.datasource.tdx_legacy" in source:
            offenders.append(str(source_file.relative_to(PROJECT_ROOT)))

    assert offenders == []
