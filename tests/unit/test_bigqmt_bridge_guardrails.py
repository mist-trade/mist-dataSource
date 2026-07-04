import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = PROJECT_ROOT / "qmt" / "builtin_bridge" / "mist_qmt_bridge.py"
SPIKE_SCRIPT = PROJECT_ROOT / "qmt" / "builtin_bridge" / "mist_qmt_spike.py"
README = PROJECT_ROOT / "README.md"
QMT_ALIGNMENT = PROJECT_ROOT / "docs" / "references" / "qmt-provider-alignment.md"
QMT_CLIENT = PROJECT_ROOT / "src" / "adapter" / "qmt" / "client.py"
ENV_EXAMPLE = PROJECT_ROOT / ".env.windows.example"


def test_qmt_production_docs_do_not_recommend_miniqmt_or_xtquant() -> None:
    scanned_files = [README, QMT_ALIGNMENT, ENV_EXAMPLE]
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


def test_builtin_bridge_polling_uses_run_time_not_market_event_callbacks() -> None:
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")

    assert ".run_time(" in source
    assert "def handlebar" not in source
    assert "subscribe_quote" not in source


def test_spike_script_is_the_only_qmt_builtin_script_allowed_to_probe_runtime_features() -> None:
    bridge_imports = _imported_top_level_names(ast.parse(BRIDGE_SCRIPT.read_text(encoding="utf-8")))
    spike_imports = _imported_top_level_names(ast.parse(SPIKE_SCRIPT.read_text(encoding="utf-8")))

    assert {"threading", "multiprocessing", "subprocess"} <= spike_imports
    assert bridge_imports.isdisjoint({"threading", "multiprocessing", "subprocess"})


def test_spike_script_records_run_time_and_websocket_evidence() -> None:
    source = SPIKE_SCRIPT.read_text(encoding="utf-8")

    assert "mist_qmt_spike_tick" in source
    assert ".run_time(" in source
    assert "tickCount" in source
    assert "websocketDuplex" in source


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
            if path.name == "mist_qmt_spike.py":
                continue
            text = path.read_text(encoding="utf-8")
            for method_name in forbidden_method_names:
                if method_name in text:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)} contains {method_name}")

    assert violations == []


def _imported_top_level_names(module: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", 1)[0])
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".", 1)[0])
    return names
