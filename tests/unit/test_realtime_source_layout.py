from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_tdx_and_qmt_share_provider_local_realtime_responsibilities() -> None:
    shared = (
        "provider.py",
        "realtime/__init__.py",
        "realtime/runtime.py",
        "realtime/contract.py",
    )
    for source in ("tdx", "qmt"):
        root = PROJECT_ROOT / "src" / "datasource" / source
        for relative in shared:
            assert (root / relative).is_file(), f"missing {source}/{relative}"


def test_tdx_and_qmt_share_route_responsibilities() -> None:
    shared = ("bridge.py", "realtime.py", "v1/dependencies.py", "v1/product.py")
    for source in ("tdx", "qmt"):
        root = PROJECT_ROOT / source / "routes"
        for relative in shared:
            assert (root / relative).is_file(), f"missing {source}/routes/{relative}"


def test_legacy_flat_and_experimental_paths_are_absent() -> None:
    forbidden = (
        "src/datasource/tdx_provider.py",
        "src/datasource/tdx_http_client.py",
        "src/datasource/tdx_models.py",
        "src/datasource/tdx_normalization.py",
        "src/datasource/qmt_provider.py",
        "src/datasource/tdx/realtime_gateway.py",
        "src/datasource/tdx/realtime_native_validator.py",
        "src/datasource/qmt/realtime.py",
        "qmt/routes/ws.py",
        "tdx/routes/realtime_bridge.py",
        "tdx/routes/realtime_ws.py",
        "qmt/builtin_bridge/mist_qmt_bridge.py",
        "qmt/builtin_bridge/mist_qmt_spike.py",
    )
    assert [path for path in forbidden if (PROJECT_ROOT / path).exists()] == []


def test_provider_specific_capabilities_remain_explicit() -> None:
    assert (PROJECT_ROOT / "src/datasource/tdx/operations/formula.py").is_file()
    assert (PROJECT_ROOT / "src/datasource/qmt/bridge.py").is_file()
    assert not (PROJECT_ROOT / "src/datasource/qmt/operations/formula.py").exists()
    assert not (PROJECT_ROOT / "src/datasource/tdx/bridge.py").exists()


def test_production_bridges_and_runtime_probe_have_distinct_identities() -> None:
    assert (
        PROJECT_ROOT / "tdx/builtin_bridge/mist_tdx_realtime_bridge.py"
    ).is_file()
    assert (
        PROJECT_ROOT / "qmt/builtin_bridge/mist_qmt_realtime_bridge.py"
    ).is_file()
    assert (
        PROJECT_ROOT / "tools/qmt_runtime_probe/mist_qmt_runtime_probe.py"
    ).is_file()
