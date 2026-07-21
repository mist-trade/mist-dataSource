from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COVERAGE_PATH = ROOT / "docs" / "references" / "tdxquant-interface-coverage.md"
QMT_ALIGNMENT_PATH = ROOT / "docs" / "references" / "qmt-provider-alignment.md"


def _coverage_text() -> str:
    return COVERAGE_PATH.read_text(encoding="utf-8")


def _coverage_row(method: str) -> str:
    prefix = f"| `{method}` |"
    for line in _coverage_text().splitlines():
        if line.startswith(prefix):
            return line
    msg = f"Coverage row for {method} was not found."
    raise AssertionError(msg)


def test_raw_tdx_call_is_documented_as_operator_debug_escape_hatch() -> None:
    text = " ".join(_coverage_text().split())

    assert "/v1/raw/tdx/call" in text
    assert "not a stable backend dependency" in text


def test_trading_and_account_methods_remain_do_not_expose() -> None:
    for method in [
        "stock_account",
        "query_stock_asset",
        "query_stock_orders",
        "query_stock_positions",
        "order_stock",
        "cancel_order_stock",
    ]:
        assert "| `do-not-expose` |" in _coverage_row(method)


def test_subscription_methods_remain_internal_only() -> None:
    for method in [
        "subscribe_hq",
        "unsubscribe_hq",
        "get_subscribe_hq_stock_list",
    ]:
        row = _coverage_row(method)
        assert "| `internal-only` |" in row
        assert "websocket" in row.lower()


def test_get_real_time_data_remains_example_helper_not_api() -> None:
    assert "| `example-helper-not-api` |" in _coverage_row("get_real_time_data")


def test_client_control_and_user_sector_mutations_remain_operator_only() -> None:
    for method in [
        "refresh_cache",
        "refresh_kline",
        "download_file",
        "exec_to_tdx",
        "send_message",
        "send_file",
        "send_warn",
        "send_bt_data",
        "create_sector",
        "delete_sector",
        "rename_sector",
        "clear_sector",
        "send_user_block",
    ]:
        row = _coverage_row(method)
        assert ("| `admin-only` |" in row) or ("| `do-not-expose` |" in row)


def test_qmt_alignment_reference_is_linked_from_coverage_matrix() -> None:
    coverage_text = _coverage_text()
    qmt_text = QMT_ALIGNMENT_PATH.read_text(encoding="utf-8")

    assert "docs/references/qmt-provider-alignment.md" in coverage_text
    assert "QMT native `marketData`" in qmt_text
    assert "`:9002/v1/bars/query`" in qmt_text
    assert "`/api/qmt/*`" not in qmt_text
    assert "`provider=qmt`" not in qmt_text
    assert "full-QMT built-in Python" in qmt_text
    assert "`get_market_data_ex(..., subscribe=False)`" in qmt_text


def test_removed_tdx_routes_are_documented() -> None:
    text = " ".join(_coverage_text().split())

    assert "`/api/tdx/*`" in text
    assert "have been removed" in text
    assert "Product callers use `/v1`" in text
