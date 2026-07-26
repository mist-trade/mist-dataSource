import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = PROJECT_ROOT / "qmt" / "builtin_bridge" / "mist_qmt_realtime_bridge.py"
RUNTIME_PROBE_SCRIPT = PROJECT_ROOT / "tools" / "qmt_runtime_probe" / "mist_qmt_runtime_probe.py"
README = PROJECT_ROOT / "README.md"
QMT_ALIGNMENT = PROJECT_ROOT / "docs" / "references" / "qmt-provider-alignment.md"
QMT_CLIENT = PROJECT_ROOT / "src" / "adapter" / "qmt" / "client.py"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
ENV_WINDOWS_EXAMPLE = PROJECT_ROOT / ".env.windows.example"
V1_PRODUCT_ROUTES = PROJECT_ROOT / "tdx" / "routes" / "v1" / "product.py"
QMT_V1_PRODUCT_ROUTES = PROJECT_ROOT / "qmt" / "routes" / "v1" / "product.py"
QMT_MAIN = PROJECT_ROOT / "qmt" / "main.py"
QMT_BRIDGE_ROUTES = PROJECT_ROOT / "qmt" / "routes" / "bridge.py"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"


def test_qmt_production_docs_do_not_recommend_miniqmt_or_xtquant() -> None:
    scanned_files = [README, QMT_ALIGNMENT, ENV_EXAMPLE, ENV_WINDOWS_EXAMPLE]
    forbidden = (
        "miniQMT",
        "MiniQMT",
        "qmttools",
        "run_strategy_file",
        "xtquant",
        "XtQuant",
        "QMT_SDK_PATH",
    )

    violations: list[str] = []
    for path in scanned_files:
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")

    assert violations == []


def test_legacy_xtquant_adapter_is_removed_from_production_path() -> None:
    assert not QMT_CLIENT.exists()


def test_builtin_bridge_uses_only_verified_stdlib_imports() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    module = ast.parse(source)
    imported_names = _imported_top_level_names(module)

    forbidden_imports = {
        "multiprocessing",
        "requests",
        "subprocess",
        "threading",
        "websocket",
        "xtquant",
    }
    assert imported_names.isdisjoint(forbidden_imports)


def test_builtin_bridge_uses_run_time_to_drain_native_subscription_callbacks() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert ".run_time(" in source
    assert "def handlebar" not in source
    assert "subscribe_quote" in source
    assert "subscribe_whole_quote" in source
    assert "unsubscribe_quote" in source
    assert "_drain_snapshot_queue()" in source


def test_builtin_bridge_loads_when_qmt_does_not_define_dunder_file() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    namespace = {"__name__": "mist_qmt_realtime_bridge_embedded"}

    class EmbeddedContext:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, str]] = []

        def run_time(self, name: str, interval: str, start_time: str) -> None:
            self.calls.append((name, interval, start_time))

    exec(compile(source, BRIDGE_SCRIPT.name, "exec"), namespace)
    context = EmbeddedContext()
    namespace["init"](context)

    assert namespace["BRIDGE_ARTIFACT_SHA256"] == "unavailable"
    assert context.calls[0][0:2] == ("mist_qmt_realtime_bridge_tick", "1nSecond")
    assert namespace["STATE"].last_error == ""


def test_builtin_bridge_run_time_starts_from_current_time_for_after_hours_smoke() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert '"2026-01-01 09:30:00"' not in source
    assert 'start_time = time.strftime("%Y-%m-%d %H:%M:%S")' in source
    assert 'ContextInfo.run_time("mist_qmt_realtime_bridge_tick", "1nSecond", start_time)' in source


def test_builtin_bridge_prints_low_frequency_tick_heartbeat_for_qmt_ui() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert "tick_count" in source
    assert "STATE.tick_count += 1" in source
    assert "mist_qmt_realtime_bridge tick" in source
    assert "STATE.tick_count <= 5" in source
    assert "STATE.tick_count % 30 == 0" in source


def test_builtin_bridge_logs_qmt_function_calls_for_qmt_ui() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert "mist_qmt_realtime_bridge command" in source
    assert "mist_qmt_realtime_bridge call_start" in source
    assert "mist_qmt_realtime_bridge call_ok" in source
    assert "mist_qmt_realtime_bridge call_error" in source
    assert "_log_command(command)" in source
    assert '_log_call_start("get_market_data_ex"' in source
    assert '_log_call_start("get_stock_list_in_sector"' in source
    assert "get_full_tick" not in source
    assert "mist_qmt_realtime_bridge control" in source


def test_qmt_builtin_scripts_default_to_qmt_service_bridge_port() -> None:
    bridge_source = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    probe_source = RUNTIME_PROBE_SCRIPT.read_text(encoding="utf-8")

    assert "http://127.0.0.1:9002/qmt/bridge" in bridge_source
    assert "http://127.0.0.1:9002/qmt/bridge" in probe_source
    assert 'STATE.gateway_url + "/health"' in probe_source
    assert "127.0.0.1:9012" not in bridge_source
    assert "127.0.0.1:9012" not in probe_source


def test_runtime_probe_is_the_only_qmt_script_allowed_to_probe_runtime_features() -> None:
    bridge_imports = _imported_top_level_names(ast.parse(BRIDGE_SCRIPT.read_text(encoding="utf-8")))
    probe_imports = _imported_top_level_names(
        ast.parse(RUNTIME_PROBE_SCRIPT.read_text(encoding="utf-8"))
    )

    assert {"threading", "multiprocessing", "subprocess"} <= probe_imports
    assert bridge_imports.isdisjoint({"threading", "multiprocessing", "subprocess"})


def test_runtime_probe_records_run_time_without_websocket_probe() -> None:
    source = RUNTIME_PROBE_SCRIPT.read_text(encoding="utf-8")

    assert "mist_qmt_runtime_probe_tick" in source
    assert ".run_time(" in source
    assert "tickCount" in source
    assert "websocket" not in source.lower()
    assert "Sec-WebSocket" not in source
    assert "spike-command-loop" not in source


def test_qmt_builtin_scripts_are_python36_compatible() -> None:
    forbidden_tokens = (
        "from __future__ import annotations",
        "dict[",
        "list[",
        "tuple[",
        " | ",
    )
    violations: list[str] = []
    for path in (BRIDGE_SCRIPT, RUNTIME_PROBE_SCRIPT):
        source = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            if token in source:
                violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {token}")

    assert violations == []


def test_ruff_keeps_qmt_builtin_scripts_python36_typing_compatible() -> None:
    source = PYPROJECT.read_text(encoding="utf-8")

    assert '"qmt/builtin_bridge/*.py"' in source
    assert '"tools/qmt_runtime_probe/*.py"' in source
    assert "F401" in source
    assert "UP006" in source
    assert "UP035" in source
    assert (
        'exclude = ["tests", "qmt/builtin_bridge", "tdx/builtin_bridge", '
        '"tools/qmt_runtime_probe"]' in source
    )


def test_runtime_probe_output_defaults_under_datasource_logs_not_c_temp() -> None:
    source = RUNTIME_PROBE_SCRIPT.read_text(encoding="utf-8")
    windows_env = ENV_WINDOWS_EXAMPLE.read_text(encoding="utf-8")

    assert "C:\\Temp" not in source
    assert "MIST_QMT_RUNTIME_PROBE_OUTPUT_PATH" in source
    assert "F:\\quant\\MistAPI\\datasource" in source
    assert "logs" in source
    assert "qmt" in source
    assert "mist_qmt_runtime_probe_output.json" in source
    assert "os.makedirs" in source
    assert (
        "MIST_QMT_RUNTIME_PROBE_OUTPUT_PATH=F:/quant/MistAPI/datasource/logs/qmt/mist_qmt_runtime_probe_output.json"
        in windows_env
    )


def test_qmt_account_and_trading_methods_are_not_exposed_by_market_datasource() -> None:
    forbidden_method_names = {
        "cancel_order",
        "get_trade_detail_data",
        "order_stock",
        "passorder",
        "query_stock_asset",
        "query_stock_orders",
        "query_stock_positions",
    }
    source_roots = [
        PROJECT_ROOT / "qmt",
        PROJECT_ROOT / "src" / "datasource" / "qmt",
        PROJECT_ROOT / "src" / "adapter" / "qmt",
    ]

    violations: list[str] = []
    for root in source_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.name == "mist_qmt_runtime_probe.py":
                continue
            text = path.read_text(encoding="utf-8")
            for method_name in forbidden_method_names:
                if method_name in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {method_name}")

    assert violations == []


def test_qmt_local_dat_binary_parsing_stays_out_of_qmt_v1_routes() -> None:
    source = QMT_V1_PRODUCT_ROUTES.read_text(encoding="utf-8")

    forbidden_route_tokens = {
        "QmtLocalDatReader",
        "struct.",
        "read_bytes",
        ".DAT",
        "86400",
        "userdata_mini",
    }
    violations = [token for token in forbidden_route_tokens if token in source]

    assert violations == []
    assert "QmtDatasourceProvider" in source


def test_retired_qmt_instance_config_stays_removed() -> None:
    assert not (PROJECT_ROOT / "qmt" / "config.py").exists()


def test_qmt_product_market_operation_never_reads_local_dat() -> None:
    source = (PROJECT_ROOT / "src" / "datasource" / "qmt" / "operations" / "market.py").read_text(
        encoding="utf-8"
    )

    assert "get_market_data_ex" in source
    assert "QmtCommandGateway" in source
    assert "QmtLocalDatReader" not in source
    assert "read_market_data" not in source


def test_tdx_v1_routes_do_not_import_or_branch_to_qmt() -> None:
    source = V1_PRODUCT_ROUTES.read_text(encoding="utf-8")

    forbidden_tokens = {
        "QmtDatasourceProvider",
        "qmt_provider",
        "provider_id",
        "qmt_operation",
        'provider == "qmt"',
        "provider=qmt",
    }

    assert [token for token in forbidden_tokens if token in source] == []


def test_qmt_service_does_not_restore_legacy_adapter_or_bridge_websocket_routes() -> None:
    main_source = QMT_MAIN.read_text(encoding="utf-8")
    bridge_source = QMT_BRIDGE_ROUTES.read_text(encoding="utf-8")

    forbidden_tokens = {
        "/api/qmt/",
        "create_qmt_adapter",
        "QMTMockAdapter",
        "QmtDataAdapter",
        "@router.websocket",
        "qmt/bridge/ws",
    }
    combined = main_source + "\n" + bridge_source

    assert [token for token in forbidden_tokens if token in combined] == []


def test_qmt_local_dat_reader_is_removed() -> None:
    assert not (PROJECT_ROOT / "src" / "datasource" / "qmt" / "local_dat.py").exists()
    config = (PROJECT_ROOT / "src" / "core" / "config.py").read_text(encoding="utf-8")
    assert "local_dat" not in config
    assert "QMT_LOCAL_DAT" not in ENV_EXAMPLE.read_text(encoding="utf-8")
    assert "QMT_LOCAL_DAT" not in ENV_WINDOWS_EXAMPLE.read_text(encoding="utf-8")


def _imported_top_level_names(module: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", 1)[0])
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".", 1)[0])
    return names
