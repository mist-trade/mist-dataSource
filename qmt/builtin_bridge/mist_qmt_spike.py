#coding:gbk
"""Full-QMT built-in Python runtime spike script.

Run this manually inside the Windows full-QMT client before enabling live QMT
provider support. It intentionally probes imports and runtime features that the
production bridge is forbidden to use.
"""

import base64
import contextlib
import importlib
import json
import multiprocessing
import os
import socket
import sqlite3
import struct
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
STATE.run_time_ticks = 0
STATE.first_tick_at = ""
STATE.last_tick_at = ""
STATE.run_time_schedule = {"ok": False, "error": "", "startTime": ""}
STATE.websocket_probe_done = False
STATE.websocket_command_loop_done = False
STATE.websocket_loop_seconds = 60


def init(ContextInfo):
    start_time = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.run_time_schedule = {"ok": False, "error": "", "startTime": start_time}
    try:
        ContextInfo.run_time("mist_qmt_spike_tick", "1nSecond", start_time)
        STATE.run_time_schedule["ok"] = True
    except Exception as exc:
        STATE.run_time_schedule["error"] = str(exc)
    run_spike(ContextInfo, "init")
    if not STATE.websocket_command_loop_done:
        STATE.results["websocketCommandLoop"] = _probe_websocket_command_loop(
            ContextInfo,
            STATE.websocket_loop_seconds,
        )
        STATE.websocket_command_loop_done = True
        _write_results(STATE.results)
        print(json.dumps(STATE.results, sort_keys=True))


def handlebar(ContextInfo):
    _ = ContextInfo


def mist_qmt_spike_tick(ContextInfo):
    _record_run_time_tick()
    if not STATE.websocket_probe_done:
        STATE.results["websocketDuplex"] = _probe_websocket_duplex()
        STATE.websocket_probe_done = True
    _write_results(STATE.results)
    if STATE.run_time_ticks <= 5 or STATE.run_time_ticks % 30 == 0:
        print(json.dumps(STATE.results, sort_keys=True))
    _ = ContextInfo


def run_spike(ContextInfo, phase):
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
        "websocketDuplex": {"ok": False, "phase": "pending-run-time-tick"},
        "websocketCommandLoop": {
            "ok": False,
            "phase": "pending-init-loop",
            "loopSeconds": STATE.websocket_loop_seconds,
        },
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
        urllib.request.urlopen("http://127.0.0.1:9012/qmt/bridge/health", timeout=1).read()
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


def _record_run_time_tick():
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    STATE.run_time_ticks += 1
    if not STATE.first_tick_at:
        STATE.first_tick_at = now
    STATE.last_tick_at = now
    STATE.results["runTime"] = _run_time_result()


def _run_time_result():
    return {
        "schedule": STATE.run_time_schedule,
        "tickCount": STATE.run_time_ticks,
        "firstTickAt": STATE.first_tick_at,
        "lastTickAt": STATE.last_tick_at,
        "outsideTradingWindowHint": _outside_trading_window_hint(),
    }


def _outside_trading_window_hint():
    local = time.localtime()
    if local.tm_wday >= 5:
        return True
    hhmm = local.tm_hour * 100 + local.tm_min
    return not ((930 <= hhmm <= 1130) or (1300 <= hhmm <= 1500))


def _probe_websocket_duplex():
    results = {
        "websocketClient": {"ok": False, "error": "not-run"},
        "stdlibRawWebSocket": {"ok": False, "error": "not-run"},
    }
    results["websocketClient"] = _probe_websocket_client_package()
    results["stdlibRawWebSocket"] = _probe_stdlib_websocket()
    results["ok"] = (
        results["websocketClient"].get("ok", False)
        or results["stdlibRawWebSocket"].get("ok", False)
    )
    return results


def _probe_websocket_client_package():
    try:
        websocket = importlib.import_module("websocket")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    connection = None
    try:
        url = "ws://127.0.0.1:9012/qmt/bridge/ws?ownerId=qmt-spike-ws-client-" + str(os.getpid())
        connection = websocket.create_connection(url, timeout=2)
        ready = connection.recv()
        connection.send(json.dumps({"type": "ping", "id": "spike-websocket-client"}))
        pong = connection.recv()
        return {"ok": True, "ready": ready, "pong": pong}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
    finally:
        if connection is not None:
            with contextlib.suppress(Exception):
                connection.close()


def _probe_stdlib_websocket():
    sock = None
    try:
        owner_id = "qmt-spike-stdlib-ws-" + str(os.getpid())
        path = "/qmt/bridge/ws?ownerId=" + owner_id
        sock = socket.create_connection(("127.0.0.1", 9012), timeout=2)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET " + path + " HTTP/1.1\r\n"
            "Host: 127.0.0.1:9012\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: " + key + "\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response_bytes = sock.recv(4096)
        marker = b"\r\n\r\n"
        marker_index = response_bytes.find(marker)
        if marker_index < 0:
            return {"ok": False, "error": "websocket handshake response missing header terminator"}
        headers = response_bytes[:marker_index].decode("latin1", "ignore")
        buffer = response_bytes[marker_index + len(marker):]
        if " 101 " not in headers:
            return {"ok": False, "error": "websocket handshake did not return 101", "headers": headers}
        ready, buffer = _recv_ws_text_frame(sock, buffer)
        _send_ws_text_frame(sock, json.dumps({"type": "ping", "id": "spike-stdlib"}))
        pong, _buffer = _recv_ws_text_frame(sock, buffer)
        return {"ok": True, "ready": ready, "pong": pong}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "traceback": traceback.format_exc()}
    finally:
        if sock is not None:
            with contextlib.suppress(Exception):
                sock.close()


def _probe_websocket_command_loop(ContextInfo, max_seconds):
    started = time.time()
    result = {
        "ok": False,
        "mode": "single-thread-bounded-blocking-loop",
        "loopSeconds": max_seconds,
        "startedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "finishedAt": "",
        "pid": os.getpid(),
        "threadCountBefore": threading.active_count(),
        "threadCountAfter": None,
        "ready": None,
        "commands": [],
        "done": None,
        "error": "",
    }
    sock = None
    buffer = b""
    try:
        owner_id = "qmt-spike-command-loop-" + str(os.getpid())
        path = "/qmt/bridge/ws?ownerId=" + owner_id + "&mode=spike-command-loop"
        sock = socket.create_connection(("127.0.0.1", 9012), timeout=2)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            "GET " + path + " HTTP/1.1\r\n"
            "Host: 127.0.0.1:9012\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: " + key + "\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response_bytes = sock.recv(4096)
        marker = b"\r\n\r\n"
        marker_index = response_bytes.find(marker)
        if marker_index < 0:
            result["error"] = "websocket handshake response missing header terminator"
            return result
        headers = response_bytes[:marker_index].decode("latin1", "ignore")
        buffer = response_bytes[marker_index + len(marker):]
        if " 101 " not in headers:
            result["error"] = "websocket handshake did not return 101"
            result["headers"] = headers
            return result

        ready_text, buffer = _recv_ws_text_frame(sock, buffer)
        result["ready"] = _json_loads(ready_text)
        sock.settimeout(1)
        while time.time() - started < max_seconds:
            try:
                text, buffer = _recv_ws_text_frame(sock, buffer)
            except TimeoutError:
                continue
            message = _json_loads(text)
            message_type = str(message.get("type", ""))
            if message_type == "bridge.command":
                command_result = _execute_ws_command(ContextInfo, message)
                result["commands"].append(
                    {
                        "id": message.get("id"),
                        "method": message.get("method"),
                        "ok": command_result.get("ok", False),
                    }
                )
                _send_ws_text_frame(sock, json.dumps(command_result))
                continue
            if message_type == "bridge.done":
                result["done"] = message
                result["ok"] = bool(result["commands"]) and all(
                    command.get("ok", False) for command in result["commands"]
                )
                break
            if message_type == "error":
                result["error"] = str(message)
                break
            result["error"] = "unsupported websocket message: " + str(message)
            break
        if not result["ok"] and not result["error"]:
            result["error"] = "websocket command loop timed out before bridge.done"
        return result
    except Exception as exc:
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        return result
    finally:
        result["finishedAt"] = time.strftime("%Y-%m-%d %H:%M:%S")
        result["threadCountAfter"] = threading.active_count()
        if sock is not None:
            with contextlib.suppress(Exception):
                sock.close()


def _execute_ws_command(ContextInfo, message):
    command_id = message.get("id")
    method = str(message.get("method", ""))
    params = message.get("params", {}) or {}
    try:
        if method == "health":
            return {
                "type": "bridge.result",
                "id": command_id,
                "ok": True,
                "result": {
                    "pid": os.getpid(),
                    "threadCount": threading.active_count(),
                    "runTimeTicks": STATE.run_time_ticks,
                },
            }
        if method == "get_market_data_ex":
            data = ContextInfo.get_market_data_ex(
                params.get("fields", []),
                params.get("symbols", []),
                period=params.get("period", "1d"),
                start_time=params.get("startTime", ""),
                end_time=params.get("endTime", ""),
                count=params.get("count", -1),
                subscribe=False,
            )
            return {
                "type": "bridge.result",
                "id": command_id,
                "ok": True,
                "result": _json_safe(data),
            }
        return {
            "type": "bridge.result",
            "id": command_id,
            "ok": False,
            "error": {
                "code": "QMT_SPIKE_COMMAND_UNSUPPORTED",
                "message": "Unsupported spike command: " + method,
                "retryable": False,
                "details": {"method": method},
            },
        }
    except Exception as exc:
        return {
            "type": "bridge.result",
            "id": command_id,
            "ok": False,
            "error": {
                "code": "QMT_SPIKE_COMMAND_FAILED",
                "message": str(exc),
                "retryable": True,
                "details": {"method": method, "traceback": traceback.format_exc()},
            },
        }


def _json_loads(text):
    try:
        return json.loads(text)
    except Exception:
        return {"type": "invalid-json", "raw": text}


def _recv_ws_text_frame(sock, buffer):
    while len(buffer) < 2:
        chunk = sock.recv(4096)
        if not chunk:
            raise Exception("websocket closed before frame header")
        buffer += chunk
    first = buffer[0]
    second = buffer[1]
    opcode = first & 15
    masked = (second & 128) != 0
    length = second & 127
    index = 2
    if length == 126:
        while len(buffer) < index + 2:
            buffer += sock.recv(4096)
        length = struct.unpack("!H", buffer[index:index + 2])[0]
        index += 2
    elif length == 127:
        while len(buffer) < index + 8:
            buffer += sock.recv(4096)
        length = struct.unpack("!Q", buffer[index:index + 8])[0]
        index += 8
    mask = b""
    if masked:
        while len(buffer) < index + 4:
            buffer += sock.recv(4096)
        mask = buffer[index:index + 4]
        index += 4
    while len(buffer) < index + length:
        chunk = sock.recv(4096)
        if not chunk:
            raise Exception("websocket closed before frame payload")
        buffer += chunk
    payload = buffer[index:index + length]
    remaining = buffer[index + length:]
    if masked:
        payload = bytes(byte ^ mask[offset % 4] for offset, byte in enumerate(payload))
    if opcode == 8:
        raise Exception("websocket close frame received")
    if opcode != 1:
        raise Exception("websocket non-text frame received: " + str(opcode))
    return payload.decode("utf-8", "ignore"), remaining


def _send_ws_text_frame(sock, text):
    payload = text.encode("utf-8")
    mask = os.urandom(4)
    header = bytearray([129])
    length = len(payload)
    if length < 126:
        header.append(128 | length)
    elif length <= 65535:
        header.append(128 | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append(128 | 127)
        header.extend(struct.pack("!Q", length))
    header.extend(mask)
    masked_payload = bytearray()
    for offset, byte in enumerate(payload):
        masked_payload.append(byte ^ mask[offset % 4])
    sock.sendall(bytes(header) + bytes(masked_payload))


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


def _json_safe(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            result[str(key)] = _json_safe(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _write_results(results):
    try:
        with open(STATE.output_path, "w") as output:
            output.write(json.dumps(results, sort_keys=True, indent=2))
    except Exception as exc:
        print("failed to write spike output: " + str(exc))


def _noop():
    return None
