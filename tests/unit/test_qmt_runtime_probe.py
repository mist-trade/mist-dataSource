import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_PROBE_SCRIPT = PROJECT_ROOT / "tools" / "qmt_runtime_probe" / "mist_qmt_runtime_probe.py"
SUBSCRIPTION_INTROSPECTION_PROBE_SCRIPT = (
    PROJECT_ROOT
    / "tools"
    / "qmt_runtime_probe"
    / "mist_qmt_subscription_introspection_probe.py"
)


def _load_runtime_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mist_qmt_runtime_probe_test", RUNTIME_PROBE_SCRIPT
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_subscription_introspection_probe() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "mist_qmt_subscription_introspection_probe_test",
        SUBSCRIPTION_INTROSPECTION_PROBE_SCRIPT,
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


def test_subscription_introspection_probe_parses_with_python36_grammar() -> None:
    source = SUBSCRIPTION_INTROSPECTION_PROBE_SCRIPT.read_text(encoding="utf-8")

    ast.parse(
        source,
        filename=str(SUBSCRIPTION_INTROSPECTION_PROBE_SCRIPT),
        feature_version=(3, 6),
    )


def test_subscription_introspection_probe_never_calls_native_methods() -> None:
    calls: list[str] = []

    class FakeContext:
        def subscribe_quote(self) -> None:
            """Single subscription."""
            calls.append("subscribe_quote")

        def subscribe_whole_quote(self) -> None:
            """Whole subscription."""
            calls.append("subscribe_whole_quote")

        def subscribe_all_market(self) -> None:
            """Undocumented alias."""
            calls.append("subscribe_all_market")

        def unsubscribe_quote(self) -> None:
            """Unsubscribe."""
            calls.append("unsubscribe_quote")

        def get_market_data_ex(self) -> None:
            """Historical read."""
            calls.append("get_market_data_ex")

    module = _load_subscription_introspection_probe()
    evidence = module._build_evidence(FakeContext())
    introspection = evidence["subscriptionApiIntrospection"]

    assert calls == []
    assert evidence["readOnly"] is True
    assert evidence["nativeMethodsInvoked"] == []
    assert evidence["mutationExecuted"] is False
    assert introspection["candidateAliases"] == [
        "subscribe_all_market",
        "subscribe_whole_quote",
    ]
    for name in introspection["requiredMethods"] + introspection["candidateAliases"]:
        assert introspection["methods"][name]["getattr"]["callable"] is True


def test_subscription_introspection_probe_sanitizes_paths_and_tokens() -> None:
    module = _load_subscription_introspection_probe()

    sanitized = module._sanitize_text(
        r'C:\Users\alice\project.py leaseToken="top-secret" '
        r'Authorization: Bearer bearer-secret'
    )

    assert "alice" not in sanitized
    assert "top-secret" not in sanitized
    assert "bearer-secret" not in sanitized
    assert sanitized.count("<REDACTED>") == 2


def test_subscription_introspection_probe_writes_json_and_log_fallback(
    tmp_path: Path,
    capsys: Any,
) -> None:
    module = _load_subscription_introspection_probe()
    output_path = tmp_path / "subscription-introspection.json"
    module.OUTPUT_PATH = str(output_path)

    evidence = module.run_probe(object())

    assert json.loads(output_path.read_text(encoding="utf-8")) == evidence
    captured = capsys.readouterr().out
    assert "MIST_QMT_SUBSCRIPTION_INTROSPECTION_BEGIN" in captured
    assert "MIST_QMT_SUBSCRIPTION_INTROSPECTION_END" in captured
    assert '"mutationExecuted": false' in captured
