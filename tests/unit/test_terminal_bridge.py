"""Tests for terminal bridge callback, fencing, and reconciliation logic."""

from __future__ import annotations

import sys
from builtins import __import__ as builtin_import
from pathlib import Path
from unittest.mock import patch

# The terminal script lives outside src/ — add its dir to path.
_BRIDGE_DIR = Path(__file__).resolve().parents[2] / "tdx" / "builtin_bridge"
sys.path.insert(0, str(_BRIDGE_DIR))

# Import the module (it's a script, not a package).
import importlib  # noqa: E402

_bridge_mod = importlib.import_module("mist_tdx_realtime_bridge")



class TestTqCenterWrapper:
    def test_real_sdk_import_error_preserves_dependency_name(self) -> None:
        def import_with_missing_dependency(name, *args, **kwargs):
            if name == "tqcenter":
                raise ImportError("No module named 'numpy'")
            return builtin_import(name, *args, **kwargs)

        wrapper = _bridge_mod.TqCenterWrapper()
        with patch("builtins.__import__", side_effect=import_with_missing_dependency):
            try:
                wrapper.initialize()
            except SystemExit as exc:
                assert "No module named 'numpy'" in str(exc)
            else:
                raise AssertionError("missing tqcenter dependency must stop the bridge")

    def test_subscription_list_errors_are_not_reported_as_empty(self) -> None:
        class BrokenTq:
            def get_subscribe_hq_stock_list(self):
                raise RuntimeError("native list failed")

        wrapper = _bridge_mod.TqCenterWrapper()
        wrapper._tq = BrokenTq()
        try:
            wrapper.get_subscribe_hq_stock_list()
        except RuntimeError as exc:
            assert str(exc) == "native list failed"
        else:
            raise AssertionError("native list failure must remain observable")


def test_terminal_bridge_separates_gateway_poll_from_native_keepalive() -> None:
    assert 1.0 < _bridge_mod.POLL_INTERVAL_SECONDS < 10.0
    assert _bridge_mod.NATIVE_KEEPALIVE_INTERVAL_SECONDS >= 30.0


def test_terminal_bridge_module_loads_without_dunder_file() -> None:
    bridge_path = _BRIDGE_DIR / "mist_tdx_realtime_bridge.py"
    source = bridge_path.read_text(encoding="utf-8")
    namespace = {"__name__": "mist_tdx_realtime_bridge_embedded"}

    exec(compile(source, bridge_path.name, "exec"), namespace)

    assert namespace["BRIDGE_SCRIPT_PATH"] is None
    assert namespace["BRIDGE_ARTIFACT_SHA256"] == "unavailable"


class TestFormatCode:
    def test_prefix_to_suffix(self) -> None:
        assert _bridge_mod._format_code("SH600519") == "600519.SH"
        assert _bridge_mod._format_code("sz000001") == "000001.SZ"

    def test_already_suffix(self) -> None:
        assert _bridge_mod._format_code("600519.SH") == "600519.SH"


class TestRetryClassification:
    def test_missing_owner_requires_registration(self) -> None:
        assert _bridge_mod._requires_registration({"code": "TDX_BRIDGE_NO_OWNER"}) is True
        for code in ("TDX_BRIDGE_LEASE_INVALID", "TDX_BRIDGE_EPOCH_MISMATCH"):
            assert _bridge_mod._requires_registration({"code": code}) is False
        assert _bridge_mod._requires_registration({"code": "OTHER"}) is False

    def test_replaced_owner_exits_instead_of_reclaiming(self) -> None:
        for code in (
            "TDX_BRIDGE_LEASE_INVALID",
            "TDX_BRIDGE_EPOCH_MISMATCH",
            "TDX_BRIDGE_OWNER_RETIRED",
        ):
            assert _bridge_mod._owner_was_replaced({"code": code}) is True
        assert _bridge_mod._owner_was_replaced({"code": "TDX_BRIDGE_NO_OWNER"}) is False

    def test_gateway_delay_is_honored_and_fallback_is_bounded(self) -> None:
        assert _bridge_mod._retry_delay_seconds({"retryAfterMs": 750}, 1) == 0.75
        assert _bridge_mod._retry_delay_seconds(None, 1) == 0.25
        assert _bridge_mod._retry_delay_seconds(None, 99) == 5.0



def test_terminal_bridge_threading_guardrail() -> None:
    """A callback lock is allowed; background thread ownership is not."""
    source = (_BRIDGE_DIR / "mist_tdx_realtime_bridge.py").read_text(
        encoding="utf-8"
    )
    assert "threading.Thread(" not in source
    assert "MIST_BRIDGE_USE_FAKE_TQ" not in source
    assert "class _FakeTq" not in source


def test_snapshot_delivery_has_no_producer_identity_or_retry_loop() -> None:
    source = (_BRIDGE_DIR / "mist_tdx_realtime_bridge.py").read_text(
        encoding="utf-8"
    )
    assert "producerSequence" not in source
    assert "producer_sequence" not in source
    assert "next_producer_sequence" not in source
    assert "max_retries" not in source
    assert source.count('BRIDGE_ENDPOINT + "/snapshot"') == 1
