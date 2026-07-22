from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_active_realtime_runtime_has_no_retired_contract_names() -> None:
    retired = (
        "builtin_experimental",
        "/ws/tdx-experimental",
        "/ws/qmt-experimental",
        "tdx.experimental.snapshot",
        "qmt.experimental.snapshot",
        "ws_experimental_snapshot",
    )
    files = [
        *ROOT.glob("src/**/*.py"),
        *ROOT.glob("tdx/**/*.py"),
        *ROOT.glob("qmt/**/*.py"),
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files)
    for token in retired:
        assert token not in combined


def test_retired_realtime_runtime_files_are_absent() -> None:
    for relative in (
        "src/datasource/tdx/experimental_gateway.py",
        "src/datasource/tdx/experimental_decoder.py",
        "tdx/routes/experimental.py",
        "tdx/routes/experimental_ws.py",
    ):
        assert not (ROOT / relative).exists()
