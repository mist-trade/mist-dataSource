#coding:gbk
"""Stdlib-only full-QMT bridge script.

Paste or import this script from the full QMT built-in Python strategy editor.
It deliberately avoids third-party packages, threads, subprocesses, and local
socket listeners. The external Mist datasource owns concurrency; this script
polls one local command gateway and executes commands serially.
"""

import json
import os
import time
import traceback
import urllib.error
import urllib.request


class BridgeState:
    pass


STATE = BridgeState()
STATE.owner_id = "bigqmt-" + str(os.getpid())
STATE.gateway_url = "http://127.0.0.1:9012/qmt/bridge"
STATE.poll_interval_seconds = 1
STATE.last_error = ""
STATE.last_poll_at = ""
STATE.started_at = time.strftime("%Y-%m-%d %H:%M:%S")


def init(ContextInfo):
    """QMT entrypoint."""
    _ = ContextInfo
    try:
        ContextInfo.run_time("mist_qmt_bridge_tick", "1nSecond", "2026-01-01 09:30:00")
    except Exception:
        STATE.last_error = traceback.format_exc()


def mist_qmt_bridge_tick(ContextInfo):
    """Poll one batch of commands and post results."""
    try:
        STATE.last_poll_at = time.strftime("%Y-%m-%d %H:%M:%S")
        _register_owner()
        commands = _post_json(
            STATE.gateway_url + "/poll",
            {"ownerId": STATE.owner_id, "limit": 1},
        ).get("commands", [])
        for command in commands:
            result = _execute_command(ContextInfo, command)
            _post_json(
                STATE.gateway_url + "/result",
                {
                    "ownerId": STATE.owner_id,
                    "commandId": command.get("commandId"),
                    "ok": result.get("ok", False),
                    "result": result.get("result"),
                    "error": result.get("error"),
                },
            )
    except Exception:
        STATE.last_error = traceback.format_exc()


def _register_owner():
    return _post_json(
        STATE.gateway_url + "/owner",
        {
            "ownerId": STATE.owner_id,
            "startedAt": STATE.started_at,
            "lastPollAt": STATE.last_poll_at,
        },
    )


def _post_json(url, payload):
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        response = urllib.request.urlopen(request, timeout=2)
        response_body = response.read().decode("utf-8")
        if not response_body:
            return {}
        return json.loads(response_body)
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "error": {
                "code": "QMT_BRIDGE_GATEWAY_UNAVAILABLE",
                "message": str(exc),
                "retryable": True,
                "details": {"url": url},
            },
        }


def _execute_command(ContextInfo, command):
    method = command.get("method", "")
    params = command.get("params", {}) or {}
    try:
        if method == "health":
            return {
                "ok": True,
                "result": {
                    "ownerId": STATE.owner_id,
                    "startedAt": STATE.started_at,
                    "lastPollAt": STATE.last_poll_at,
                    "lastError": STATE.last_error,
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
            return {"ok": True, "result": _json_safe(data)}
        if method == "get_full_tick":
            data = ContextInfo.get_full_tick(params.get("symbols", []))
            return {"ok": True, "result": _json_safe(data)}
        if method == "get_stock_list_in_sector":
            data = ContextInfo.get_stock_list_in_sector(
                params.get("sector", "\u6caa\u6df1A\u80a1")
            )
            return {"ok": True, "result": _json_safe(data)}
        return {
            "ok": False,
            "error": {
                "code": "QMT_COMMAND_UNSUPPORTED",
                "message": "Unsupported QMT bridge command: " + method,
                "retryable": False,
                "details": {"method": method},
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": {
                "code": "QMT_COMMAND_FAILED",
                "message": str(exc),
                "retryable": True,
                "details": {"method": method, "traceback": traceback.format_exc()},
            },
        }


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
