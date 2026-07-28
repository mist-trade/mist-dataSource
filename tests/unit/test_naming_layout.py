from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_realtime_gateways_use_the_same_provider_relative_path() -> None:
    assert (ROOT / "src/datasource/tdx/realtime/gateway.py").is_file()
    assert (ROOT / "src/datasource/qmt/realtime/gateway.py").is_file()
    assert not (ROOT / "src/datasource/tdx/realtime/runtime.py").exists()
    assert not (ROOT / "src/datasource/qmt/bridge.py").exists()


def test_tdx_market_normalization_has_a_specific_name() -> None:
    assert (ROOT / "src/datasource/tdx/market_normalization.py").is_file()
    assert not (ROOT / "src/datasource/tdx/normalization.py").exists()


def test_retired_readiness_names_are_absent_from_active_code() -> None:
    active_roots = (ROOT / "tdx", ROOT / "qmt", ROOT / "src")
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for active_root in active_roots
        for path in active_root.rglob("*.py")
    )

    assert "tdxRealtimeBridgeReady" not in source
    assert "collectorReady" not in source
    assert "datasourceBuildId" not in source
