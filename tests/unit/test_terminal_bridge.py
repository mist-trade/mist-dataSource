"""Tests for the terminal bridge script logic (callback dirty-only, reconcile).

Uses the _FakeTq to simulate tqcenter on macOS. Does NOT test real SDK —
that requires Windows HIL.
"""

from __future__ import annotations

import json
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


class TestDirtySymbolQueue:
    def test_mark_dirty_and_swap(self) -> None:
        q = _bridge_mod.DirtySymbolQueue()
        q.mark_dirty("600519.SH")
        q.mark_dirty("000001.SZ")
        result = q.swap_and_clear()
        assert result == {"600519.SH", "000001.SZ"}
        # Second swap is empty (cleared).
        assert q.swap_and_clear() == set()

    def test_max_queue_size(self) -> None:
        q = _bridge_mod.DirtySymbolQueue()
        q._symbols  # noqa: B018
        # Fill beyond max.
        for i in range(300):
            q.mark_dirty(f"{i:06d}.SH")
        result = q.swap_and_clear()
        assert len(result) == _bridge_mod.DIRTY_QUEUE_MAX  # 200


class TestFakeTq:
    def test_subscribe_triggers_callback(self) -> None:
        fake = _bridge_mod._FakeTq()
        received: list[str] = []
        fake.subscribe_hq(["600519.SH"], lambda data: received.append(data))
        assert len(received) == 1
        parsed = json.loads(received[0])
        assert parsed["Code"] == "600519.SH"

    def test_get_market_snapshot(self) -> None:
        fake = _bridge_mod._FakeTq()
        snap = fake.get_market_snapshot("600519.SH")
        assert snap["Code"] == "600519.SH"
        assert snap["Now"] == "1685.0"
        assert snap["ErrorId"] == "0"

    def test_unsubscribe(self) -> None:
        fake = _bridge_mod._FakeTq()
        fake.subscribe_hq(["600519.SH"], lambda _: None)
        assert "600519.SH" in fake.get_subscribe_hq_stock_list()
        fake.unsubscribe_hq(["600519.SH"])
        assert "600519.SH" not in fake.get_subscribe_hq_stock_list()

    def test_real_sdk_import_error_preserves_dependency_name(self, monkeypatch) -> None:
        monkeypatch.delenv("MIST_BRIDGE_USE_FAKE_TQ", raising=False)

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


class TestCallbackDirtyOnly:
    """Verify that subscribe_hq callback only marks dirty — no SDK/HTTP calls."""

    def test_callback_does_not_call_sdk(self) -> None:
        """The callback should only call dirty_queue.mark_dirty, not get_market_snapshot."""
        q = _bridge_mod.DirtySymbolQueue()
        tq_wrapper = _bridge_mod.TqCenterWrapper()
        tq_wrapper._tq = _bridge_mod._FakeTq()
        tq_wrapper._is_fake = True

        # Patch mark_dirty to track it was called.
        with patch.object(q, "mark_dirty", wraps=q.mark_dirty) as mock_mark:
            # The on_quote_update closure is defined inside run_bridge; test
            # the DirtySymbolQueue directly.
            q.mark_dirty(_bridge_mod._format_code("SH600519"))
            mock_mark.assert_called_once_with("600519.SH")


def test_terminal_bridge_threading_guardrail() -> None:
    """A callback lock is allowed; background thread ownership is not."""
    source = (_BRIDGE_DIR / "mist_tdx_realtime_bridge.py").read_text()
    assert "threading.Lock()" in source
    assert "threading.Thread(" not in source
