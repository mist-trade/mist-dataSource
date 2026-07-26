# coding:gbk
"""Full-QMT built-in Python runtime probe script.

Run this manually inside the Windows full-QMT client before enabling live QMT
provider support. It intentionally probes imports and runtime features that the
production bridge is forbidden to use.
"""

import importlib
import inspect
import io
import json
import multiprocessing
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from contextlib import redirect_stdout
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, cast

if TYPE_CHECKING:
    from typing import Protocol

    class RuntimeProbeContextInfo(Protocol):
        """Subset used by this runtime probe; attributes follow ThinkTrader ContextInfo docs."""

        stockcode: str
        market: str
        period: str

        def run_time(self, func_name: str, period: str, start_time: str) -> Any: ...

        def get_market_data_ex(
            self,
            fields: Any,
            stock_list: Any,
            *,
            period: Any,
            count: Any,
            subscribe: bool,
        ) -> Any: ...
else:
    RuntimeProbeContextInfo = Any


class RuntimeProbeState:
    output_path: str
    gateway_url: str
    results: Dict[str, Any]
    run_time_ticks: int
    first_tick_at: str
    last_tick_at: str
    run_time_schedule: Dict[str, Any]


DEFAULT_DATASOURCE_ROOT = r"F:\quant\MistAPI\datasource"
DEFAULT_RUNTIME_PROBE_OUTPUT_NAME = "mist_qmt_runtime_probe_output.json"
INTROSPECTION_TEXT_LIMIT = 8192
SUBSCRIPTION_INTROSPECTION_METHODS = (
    "subscribe_quote",
    "subscribe_whole_quote",
    "unsubscribe_quote",
    "get_market_data_ex",
)


def _default_output_path() -> str:
    configured_path = os.environ.get("MIST_QMT_RUNTIME_PROBE_OUTPUT_PATH", "").strip()
    if configured_path:
        return configured_path
    datasource_root = os.environ.get("MIST_DATASOURCE_ROOT", DEFAULT_DATASOURCE_ROOT).strip()
    if not datasource_root:
        datasource_root = DEFAULT_DATASOURCE_ROOT
    return os.path.join(datasource_root, "logs", "qmt", DEFAULT_RUNTIME_PROBE_OUTPUT_NAME)


STATE = RuntimeProbeState()
STATE.output_path = _default_output_path()
STATE.gateway_url = os.environ.get("QMT_BRIDGE_GATEWAY_URL", "http://127.0.0.1:9002/qmt/bridge")
STATE.results = {}
STATE.run_time_ticks = 0
STATE.first_tick_at = ""
STATE.last_tick_at = ""
STATE.run_time_schedule = {"ok": False, "error": "", "startTime": ""}


def init(ContextInfo: RuntimeProbeContextInfo) -> None:
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.run_time_schedule = {"ok": False, "error": "", "startTime": start_time}
    try:
        ContextInfo.run_time("mist_qmt_runtime_probe_tick", "1nSecond", start_time)
        STATE.run_time_schedule["ok"] = True
    except Exception as exc:
        STATE.run_time_schedule["error"] = str(exc)
    run_runtime_probe(ContextInfo, "init")


def handlebar(ContextInfo: RuntimeProbeContextInfo) -> None:
    _ = ContextInfo


def mist_qmt_runtime_probe_tick(ContextInfo: RuntimeProbeContextInfo) -> None:
    _record_run_time_tick()
    _write_results(STATE.results)
    if STATE.run_time_ticks <= 5 or STATE.run_time_ticks % 30 == 0:
        print(json.dumps(STATE.results, sort_keys=True))
    _ = ContextInfo


def run_runtime_probe(ContextInfo: RuntimeProbeContextInfo, phase: str) -> None:
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "phase": phase,
        "pythonVersion": sys.version,
        "pid": os.getpid(),
        "imports": _probe_imports(),
        "sqlite": _probe_sqlite(),
        "network": _probe_network(),
        "processModel": _probe_process_model(),
        "runTime": _run_time_result(),
        "nativeApi": _probe_native_api(ContextInfo),
        "subscriptionApiIntrospection": _probe_subscription_api_introspection(ContextInfo),
    }
    STATE.results = results
    _write_results(results)
    print(json.dumps(results, sort_keys=True))


def _probe_imports() -> Dict[str, Any]:
    names = [
        "json",
        "urllib",
        "http.client",
        "socket",
        "sqlite3",
        "requests",
    ]
    results = {}  # type: Dict[str, Any]
    for name in names:
        try:
            importlib.import_module(name)
            results[name] = {"ok": True, "error": ""}
        except Exception as exc:
            results[name] = {"ok": False, "error": str(exc)}
    return results


def _probe_sqlite() -> Dict[str, Any]:
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("select 1")
        connection.close()
        return {"ok": True, "error": ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _probe_network() -> Dict[str, Any]:
    results = {}  # type: Dict[str, Any]
    try:
        urllib.request.urlopen(STATE.gateway_url + "/health", timeout=1).read()
        results["outboundLocalHttp"] = {"ok": True, "error": ""}
    except Exception as exc:
        results["outboundLocalHttp"] = {"ok": False, "error": str(exc)}

    try:
        requests = cast(Any, importlib.import_module("requests"))
        response = requests.get(STATE.gateway_url + "/health", timeout=1)
        results["requestsLocalHttp"] = {
            "ok": 200 <= response.status_code < 300,
            "statusCode": response.status_code,
            "error": "",
        }
    except Exception as exc:
        results["requestsLocalHttp"] = {"ok": False, "error": str(exc)}

    listener: Any = None
    try:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        results["listenLocalPort"] = {"ok": True, "error": ""}
    except Exception as exc:
        results["listenLocalPort"] = {"ok": False, "error": str(exc)}
    finally:
        if listener is not None:
            listener.close()
    return results


def _probe_process_model() -> Dict[str, Any]:
    results = {
        "mainThread": str(threading.current_thread()),
        "activeThreadCount": threading.active_count(),
    }
    try:
        thread_result = []  # type: List[int]

        def target() -> None:
            thread_result.append(os.getpid())

        worker = threading.Thread(target=target)
        worker.start()
        worker.join(1)
        results["threading"] = {"ok": True, "result": thread_result}
    except Exception as exc:
        results["threading"] = {"ok": False, "error": str(exc)}

    try:
        process = multiprocessing.Process(target=_noop)
        process.start()
        process.join(1)
        results["multiprocessing"] = {"ok": True, "exitcode": process.exitcode}
    except Exception as exc:
        results["multiprocessing"] = {"ok": False, "error": str(exc)}

    try:
        completed = subprocess.Popen(
            [sys.executable, "-c", "print('qmt-subprocess-probe')"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = completed.communicate(timeout=2)
        results["subprocess"] = {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": stdout.decode("utf-8", "ignore"),
            "stderr": stderr.decode("utf-8", "ignore"),
        }
    except Exception as exc:
        results["subprocess"] = {"ok": False, "error": str(exc)}
    return results


def _record_run_time_tick() -> None:
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.run_time_ticks += 1
    if not STATE.first_tick_at:
        STATE.first_tick_at = now
    STATE.last_tick_at = now
    STATE.results["runTime"] = _run_time_result()


def _run_time_result() -> Dict[str, Any]:
    return {
        "schedule": STATE.run_time_schedule,
        "tickCount": STATE.run_time_ticks,
        "firstTickAt": STATE.first_tick_at,
        "lastTickAt": STATE.last_tick_at,
        "outsideTradingWindowHint": _outside_trading_window_hint(),
    }


def _outside_trading_window_hint() -> bool:
    local = time.localtime()
    if local.tm_wday >= 5:
        return True
    hhmm = local.tm_hour * 100 + local.tm_min
    return not ((930 <= hhmm <= 1130) or (1300 <= hhmm <= 1500))


def _probe_native_api(ContextInfo: RuntimeProbeContextInfo) -> Dict[str, Any]:
    results = {}  # type: Dict[str, Any]
    try:
        results["stock"] = {
            "ok": True,
            "value": str(ContextInfo.stockcode) + "." + str(ContextInfo.market),
        }
    except Exception as exc:
        results["stock"] = {"ok": False, "error": str(exc)}
    try:
        data = ContextInfo.get_market_data_ex(
            ["close"],
            [str(ContextInfo.stockcode) + "." + str(ContextInfo.market)],
            period=ContextInfo.period,
            count=1,
            subscribe=False,
        )
        results["get_market_data_ex"] = {"ok": True, "value": str(data)}
    except Exception as exc:
        results["get_market_data_ex"] = {
            "ok": False,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }
    return results


def _probe_subscription_api_introspection(
    ContextInfo: RuntimeProbeContextInfo,
) -> Dict[str, Any]:
    directory_names = []  # type: List[str]
    directory_error = ""
    try:
        directory_names = sorted(str(name) for name in dir(ContextInfo))
    except Exception as exc:
        directory_error = _error_text(exc)

    candidate_aliases = [
        name
        for name in directory_names
        if name.lower().startswith("subscribe")
        and ("all" in name.lower() or "whole" in name.lower())
    ]
    method_names = []  # type: List[str]
    for name in list(SUBSCRIPTION_INTROSPECTION_METHODS) + candidate_aliases:
        if name not in method_names:
            method_names.append(name)

    methods = {}  # type: Dict[str, Any]
    for name in method_names:
        methods[name] = _introspect_attribute(ContextInfo, name, name in directory_names)

    return {
        "dir": {
            "ok": not directory_error,
            "names": directory_names,
            "error": directory_error,
        },
        "requiredMethods": list(SUBSCRIPTION_INTROSPECTION_METHODS),
        "candidateAliases": candidate_aliases,
        "methods": methods,
    }


def _introspect_attribute(target: Any, name: str, listed_in_dir: bool) -> Dict[str, Any]:
    try:
        value = getattr(target, name)
    except Exception as exc:
        return {
            "listedInDir": listed_in_dir,
            "getattr": {
                "ok": False,
                "found": False,
                "callable": False,
                "type": "",
                "error": _error_text(exc),
            },
            "__doc__": {"status": "unknown", "value": "", "error": "getattr failed"},
            "help": {"status": "unknown", "value": "", "error": "getattr failed"},
            "signature": {"status": "unknown", "value": "", "error": "getattr failed"},
        }

    result = {
        "listedInDir": listed_in_dir,
        "getattr": {
            "ok": True,
            "found": True,
            "callable": callable(value),
            "type": type(value).__name__,
            "error": "",
        },
    }  # type: Dict[str, Any]
    result["__doc__"] = _introspect_doc(value)
    result["help"] = _introspect_help(value)
    result["signature"] = _introspect_signature(value)
    return result


def _introspect_doc(value: Any) -> Dict[str, str]:
    try:
        doc = getattr(value, "__doc__", None)
        if doc is None:
            return {"status": "missing", "value": "", "error": ""}
        return {"status": "known", "value": _bounded_text(doc), "error": ""}
    except Exception as exc:
        return {"status": "unknown", "value": "", "error": _error_text(exc)}


def _introspect_help(value: Any) -> Dict[str, str]:
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            help(value)
        return {"status": "known", "value": _bounded_text(output.getvalue()), "error": ""}
    except Exception as exc:
        return {
            "status": "unknown",
            "value": _bounded_text(output.getvalue()),
            "error": _error_text(exc),
        }


def _introspect_signature(value: Any) -> Dict[str, str]:
    try:
        return {
            "status": "known",
            "value": _bounded_text(inspect.signature(value)),
            "error": "",
        }
    except Exception as exc:
        return {"status": "unknown", "value": "", "error": _error_text(exc)}


def _bounded_text(value: Any) -> str:
    text = str(value)
    if len(text) <= INTROSPECTION_TEXT_LIMIT:
        return text
    return text[:INTROSPECTION_TEXT_LIMIT] + "...[truncated]"


def _error_text(exc: Exception) -> str:
    return type(exc).__name__ + ": " + _bounded_text(exc)


def _json_safe(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, dict):
        result = {}  # type: Dict[str, Any]
        mapping = cast(Mapping[Any, Any], value)
        for key, item in mapping.items():
            result[str(key)] = _json_safe(item)
        return result
    if isinstance(value, (list, tuple)):
        sequence = cast(Any, value)
        return [_json_safe(item) for item in sequence]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _write_results(results: Mapping[str, Any]) -> None:
    try:
        output_dir = os.path.dirname(STATE.output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        with open(STATE.output_path, "w") as output:
            output.write(json.dumps(results, sort_keys=True, indent=2))
    except Exception as exc:
        print("failed to write runtime probe output: " + str(exc))


def _noop() -> None:
    return None
