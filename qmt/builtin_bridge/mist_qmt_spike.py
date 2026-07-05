#coding:gbk
"""Full-QMT built-in Python runtime spike script.

Run this manually inside the Windows full-QMT client before enabling live QMT
provider support. It intentionally probes imports and runtime features that the
production bridge is forbidden to use.
"""

import importlib
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
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, cast

if TYPE_CHECKING:
    from typing import Protocol

    class SpikeContextInfo(Protocol):
        """Subset used by this spike; attributes follow ThinkTrader ContextInfo docs."""

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
    SpikeContextInfo = Any


class SpikeState:
    output_path: str
    gateway_url: str
    results: Dict[str, Any]
    run_time_ticks: int
    first_tick_at: str
    last_tick_at: str
    run_time_schedule: Dict[str, Any]


DEFAULT_DATASOURCE_ROOT = r"F:\quant\MistAPI\datasource"
DEFAULT_SPIKE_OUTPUT_NAME = "mist_qmt_spike_output.json"


def _default_output_path() -> str:
    configured_path = os.environ.get("MIST_QMT_SPIKE_OUTPUT_PATH", "").strip()
    if configured_path:
        return configured_path
    datasource_root = os.environ.get("MIST_DATASOURCE_ROOT", DEFAULT_DATASOURCE_ROOT).strip()
    if not datasource_root:
        datasource_root = DEFAULT_DATASOURCE_ROOT
    return os.path.join(datasource_root, "logs", "qmt", DEFAULT_SPIKE_OUTPUT_NAME)


STATE = SpikeState()
STATE.output_path = _default_output_path()
STATE.gateway_url = os.environ.get("QMT_BRIDGE_GATEWAY_URL", "http://127.0.0.1:9002/qmt/bridge")
STATE.results = {}
STATE.run_time_ticks = 0
STATE.first_tick_at = ""
STATE.last_tick_at = ""
STATE.run_time_schedule = {"ok": False, "error": "", "startTime": ""}


def init(ContextInfo: SpikeContextInfo) -> None:
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.run_time_schedule = {"ok": False, "error": "", "startTime": start_time}
    try:
        ContextInfo.run_time("mist_qmt_spike_tick", "1nSecond", start_time)
        STATE.run_time_schedule["ok"] = True
    except Exception as exc:
        STATE.run_time_schedule["error"] = str(exc)
    run_spike(ContextInfo, "init")


def handlebar(ContextInfo: SpikeContextInfo) -> None:
    _ = ContextInfo


def mist_qmt_spike_tick(ContextInfo: SpikeContextInfo) -> None:
    _record_run_time_tick()
    _write_results(STATE.results)
    if STATE.run_time_ticks <= 5 or STATE.run_time_ticks % 30 == 0:
        print(json.dumps(STATE.results, sort_keys=True))
    _ = ContextInfo


def run_spike(ContextInfo: SpikeContextInfo, phase: str) -> None:
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


def _probe_native_api(ContextInfo: SpikeContextInfo) -> Dict[str, Any]:
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
        print("failed to write spike output: " + str(exc))


def _noop() -> None:
    return None
