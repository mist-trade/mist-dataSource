import queue
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SCRIPT = PROJECT_ROOT / "qmt" / "builtin_bridge" / "mist_qmt_realtime_bridge.py"


def _bridge_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "mist_qmt_realtime_bridge_subscription_test"}
    source = BRIDGE_SCRIPT.read_text(encoding="utf-8")
    exec(compile(source, BRIDGE_SCRIPT.name, "exec"), namespace)
    namespace["STATE"].owner_id = "bigqmt-test"
    namespace["STATE"].lease_token = "secret-test-token"
    namespace["STATE"].generation = 3
    return namespace


def test_bridge_dispatches_three_exact_native_subscription_calls() -> None:
    namespace = _bridge_namespace()

    class Context:
        def __init__(self) -> None:
            self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
            self.callbacks: list[Any] = []

        def subscribe_quote(self, *args: Any, **kwargs: Any) -> int:
            self.calls.append(("subscribe_quote", args, kwargs))
            self.callbacks.append(kwargs["callback"])
            return 0

        def subscribe_whole_quote(self, *args: Any, **kwargs: Any) -> int:
            self.calls.append(("subscribe_whole_quote", args, kwargs))
            self.callbacks.append(kwargs["callback"])
            return -9

        def unsubscribe_quote(self, *args: Any, **kwargs: Any) -> int:
            self.calls.append(("unsubscribe_quote", args, kwargs))
            return 1

    context = Context()
    execute = namespace["_execute_subscription_command"]

    assert execute(
        context,
        {"callSequence": 1, "method": "subscribe_quote", "symbol": "300502.SZ"},
    ) == {"success": 0}
    assert execute(
        context,
        {
            "callSequence": 2,
            "method": "subscribe_whole_quote",
            "symbols": ["300502.SZ", "600030.SH"],
        },
    ) == {"success": -9}
    assert execute(
        context,
        {
            "callSequence": 3,
            "method": "unsubscribe_quote",
            "subId": 0,
            "symbol": "300502.SZ",
        },
    ) == {"success": 1}

    assert context.calls[0][0:2] == ("subscribe_quote", ("300502.SZ",))
    assert context.calls[0][2] == {
        "period": "tick",
        "dividend_type": "none",
        "result_type": "dict",
        "callback": context.callbacks[0],
    }
    assert context.calls[1][0:2] == (
        "subscribe_whole_quote",
        (["300502.SZ", "600030.SH"],),
    )
    assert context.calls[1][2] == {"callback": context.callbacks[1]}
    assert context.calls[2] == ("unsubscribe_quote", (0,), {})


def test_runtime_introspection_reads_active_subscription_inventory() -> None:
    namespace = _bridge_namespace()

    class Context:
        def get_all_subscription(self) -> dict[str, Any]:
            return {
                "subscribe_quote": {
                    "stock_code": "600519.SH",
                    "period": "tick",
                }
            }

    result = namespace["_runtime_introspection"](Context())

    assert result["methods"]["get_all_subscription"]["available"] is True
    assert result["activeSubscriptionObservation"] == {
        "available": True,
        "ok": True,
        "result": {
            "subscribe_quote": {
                "stock_code": "600519.SH",
                "period": "tick",
            }
        },
        "error": None,
    }


def test_runtime_introspection_reports_missing_active_subscription_inventory() -> None:
    namespace = _bridge_namespace()

    result = namespace["_runtime_introspection"](object())

    assert result["methods"]["get_all_subscription"]["available"] is False
    assert result["activeSubscriptionObservation"] == {
        "available": False,
        "ok": False,
        "result": None,
        "error": None,
    }


def test_callback_stores_latest_slot_and_runtime_flush_posts_one_complete_map() -> None:
    namespace = _bridge_namespace()
    namespace["QMT_BRIDGE_TRANSPORT"] = "http"
    posted: list[tuple[str, dict[str, Any]]] = []
    namespace["_post_json"] = lambda url, payload: posted.append((url, dict(payload))) or {}

    class Context:
        def __init__(self) -> None:
            self.callback: Any = None

        def subscribe_whole_quote(self, _symbols: list[str], *, callback: Any) -> int:
            self.callback = callback
            return 12

    context = Context()
    result = namespace["_execute_subscription_command"](
        context,
        {
            "callSequence": 1,
            "method": "subscribe_whole_quote",
            "symbols": ["300502.SZ", "600030.SH"],
        },
    )
    assert result == {"success": 12}

    context.callback(
        {
            "300502.SZ": {"lastPrice": 10.5, "bidPrice": [10.4]},
            "600030.SH": {"lastPrice": 20.5, "bidPrice": [20.4]},
        }
    )
    # E: single-slot latest per symbol — no business queue, nothing posted yet.
    assert posted == []
    assert set(namespace["STATE"].latest) == {"300502.SZ", "600030.SH"}

    # Flush deduplicates the shared callback item into one POST.
    assert namespace["_flush_latest"]() == 1
    assert len(posted) == 1
    url, payload = posted[0]
    assert url.endswith("/subscriptions/snapshot")
    assert set(payload) == {
        "ownerId",
        "leaseToken",
        "generation",
        "subscriptionId",
        "capturedAt",
        "native",
    }
    assert payload["subscriptionId"] == 12
    assert payload["native"] == {
        "300502.SZ": {"lastPrice": 10.5, "bidPrice": [10.4]},
        "600030.SH": {"lastPrice": 20.5, "bidPrice": [20.4]},
    }
    # Flushed: slots cleared, no second POST.
    assert namespace["STATE"].latest == {}
    assert namespace["_flush_latest"]() == 0
    assert len(posted) == 1


def test_callback_drops_unsafe_entry_and_latest_slot_overwrites() -> None:
    namespace = _bridge_namespace()

    class Unsafe:
        pass

    namespace["_enqueue_callback_snapshot"](
        7,
        {
            "300502.SZ": {"lastPrice": 10.5},
            "600030.SH": Unsafe(),
        },
    )
    # Unsafe entry rejected; safe symbol stored in its latest slot.
    assert set(namespace["STATE"].latest) == {"300502.SZ"}
    item = namespace["STATE"].latest["300502.SZ"]
    assert item["native"] == {"300502.SZ": {"lastPrice": 10.5}}

    # A newer callback overwrites the slot (no queue growth) and counts a merge.
    namespace["_enqueue_callback_snapshot"](
        7,
        {"300502.SZ": {"lastPrice": 10.6}},
    )
    assert set(namespace["STATE"].latest) == {"300502.SZ"}
    assert namespace["STATE"].merged_count == 1
    assert namespace["STATE"].latest["300502.SZ"]["native"] == {
        "300502.SZ": {"lastPrice": 10.6}
    }


def test_bridge_contains_missing_method_exception_and_unknown_command_fields() -> None:
    namespace = _bridge_namespace()

    class Context:
        pass

    missing = namespace["_execute_subscription_command"](
        Context(),
        {"callSequence": 1, "method": "subscribe_quote", "symbol": "300502.SZ"},
    )
    unknown = namespace["_execute_subscription_command"](
        Context(),
        {
            "callSequence": 2,
            "method": "unsubscribe_quote",
            "subId": 1,
            "symbol": "300502.SZ",
            "leaseToken": "must-not-be-in-command",
        },
    )

    assert missing == {
        "failure": {
            "symbol": "300502.SZ",
            "reason": "QMT_NATIVE_METHOD_MISSING",
        }
    }
    assert unknown == {
        "failure": {
            "symbol": "300502.SZ",
            "reason": "QMT_NATIVE_COMMAND_INVALID",
        }
    }
