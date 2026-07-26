import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PROBE_SCRIPT = PROJECT_ROOT / "tools" / "qmt_runtime_probe" / "mist_qmt_runtime_probe.py"


def _load_runtime_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mist_qmt_runtime_probe_test", RUNTIME_PROBE_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runtime_probe_parses_with_python36_grammar() -> None:
    source = RUNTIME_PROBE_SCRIPT.read_text(encoding="utf-8")

    ast.parse(source, filename=str(RUNTIME_PROBE_SCRIPT), feature_version=(3, 6))


def test_subscription_introspection_records_required_methods_and_aliases_without_calling() -> None:
    calls: list[str] = []

    class FakeContext:
        def subscribe_quote(self, _stock_code: str, _period: str) -> int:
            """Subscribe one quote stream."""
            calls.append("subscribe_quote")
            raise AssertionError("introspection must not call subscribe_quote")

        def subscribe_whole_quote(self, _market: str) -> int:
            """Subscribe a whole-market quote stream."""
            calls.append("subscribe_whole_quote")
            raise AssertionError("introspection must not call subscribe_whole_quote")

        def unsubscribe_quote(self, _subscription_id: int) -> None:
            """Cancel one quote subscription."""
            calls.append("unsubscribe_quote")
            raise AssertionError("introspection must not call unsubscribe_quote")

        def get_market_data_ex(self, _fields: list[str], _stock_list: list[str]) -> dict:
            """Read historical market data."""
            calls.append("get_market_data_ex")
            raise AssertionError("introspection must not call get_market_data_ex")

        def subscribe_all_market(self, _market: str) -> int:
            """Candidate all-market alias."""
            calls.append("subscribe_all_market")
            raise AssertionError("introspection must not call subscribe_all_market")

        def subscribe_whole_market_v2(self, _market: str) -> int:
            """Candidate whole-market alias."""
            calls.append("subscribe_whole_market_v2")
            raise AssertionError("introspection must not call subscribe_whole_market_v2")

    module = _load_runtime_probe()
    result = module._probe_subscription_api_introspection(FakeContext())

    assert result["dir"]["ok"] is True
    assert result["requiredMethods"] == [
        "subscribe_quote",
        "subscribe_whole_quote",
        "unsubscribe_quote",
        "get_market_data_ex",
    ]
    assert result["candidateAliases"] == [
        "subscribe_all_market",
        "subscribe_whole_market_v2",
        "subscribe_whole_quote",
    ]
    assert calls == []

    for name in result["requiredMethods"] + result["candidateAliases"]:
        method = result["methods"][name]
        assert method["getattr"]["found"] is True
        assert method["getattr"]["callable"] is True
        assert method["__doc__"]["status"] == "known"
        assert method["help"]["status"] == "known"
        assert method["signature"]["status"] == "known"

    json.dumps(result)


def test_signature_failure_is_recorded_as_unknown_without_hiding_attribute() -> None:
    calls: list[str] = []

    class UnknownSignatureCallable:
        @property
        def __signature__(self) -> object:
            raise ValueError("native signature is unavailable")

        def __call__(self) -> None:
            calls.append("subscribe_quote")
            raise AssertionError("introspection must not call the native method")

    class FakeContext:
        subscribe_quote = UnknownSignatureCallable()

    module = _load_runtime_probe()
    result = module._probe_subscription_api_introspection(FakeContext())
    method = result["methods"]["subscribe_quote"]

    assert method["getattr"]["found"] is True
    assert method["getattr"]["callable"] is True
    assert method["signature"]["status"] == "unknown"
    assert "ValueError: native signature is unavailable" in method["signature"]["error"]
    assert calls == []
