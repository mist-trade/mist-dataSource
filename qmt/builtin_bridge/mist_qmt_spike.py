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


class SpikeState:
    pass


STATE = SpikeState()
STATE.output_path = "mist_qmt_spike_output.json"
STATE.results = {}


def init(ContextInfo):
    _ = ContextInfo
    run_spike(ContextInfo)


def handlebar(ContextInfo):
    _ = ContextInfo


def run_spike(ContextInfo):
    results = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pythonVersion": sys.version,
        "pid": os.getpid(),
        "imports": _probe_imports(),
        "sqlite": _probe_sqlite(),
        "network": _probe_network(),
        "processModel": _probe_process_model(),
        "nativeApi": _probe_native_api(ContextInfo),
    }
    STATE.results = results
    _write_results(results)
    print(json.dumps(results, sort_keys=True))


def _probe_imports():
    names = [
        "json",
        "urllib",
        "http.client",
        "socket",
        "sqlite3",
        "requests",
        "websocket",
        "websocket_client",
    ]
    results = {}
    for name in names:
        try:
            importlib.import_module(name)
            results[name] = {"ok": True, "error": ""}
        except Exception as exc:
            results[name] = {"ok": False, "error": str(exc)}
    return results


def _probe_sqlite():
    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("select 1")
        connection.close()
        return {"ok": True, "error": ""}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _probe_network():
    results = {}
    try:
        urllib.request.urlopen("http://127.0.0.1:9012/health", timeout=1).read()
        results["outboundLocalHttp"] = {"ok": True, "error": ""}
    except Exception as exc:
        results["outboundLocalHttp"] = {"ok": False, "error": str(exc)}

    listener = None
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


def _probe_process_model():
    results = {
        "mainThread": str(threading.current_thread()),
        "activeThreadCount": threading.active_count(),
    }
    try:
        thread_result = []

        def target():
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


def _probe_native_api(ContextInfo):
    results = {}
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


def _write_results(results):
    try:
        with open(STATE.output_path, "w") as output:
            output.write(json.dumps(results, sort_keys=True, indent=2))
    except Exception as exc:
        print("failed to write spike output: " + str(exc))


def _noop():
    return None
