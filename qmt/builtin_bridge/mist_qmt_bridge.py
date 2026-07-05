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
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, cast

if TYPE_CHECKING:
    from typing import Protocol

    class BridgeContextInfo(Protocol):
        """Subset used by this bridge; attributes follow ThinkTrader ContextInfo docs."""

        def run_time(self, func_name: str, period: str, start_time: str) -> Any: ...

        def get_market_data_ex(
            self,
            fields: Any,
            stock_list: Any,
            *,
            period: Any,
            start_time: Any,
            end_time: Any,
            count: Any,
            dividend_type: Any,
            fill_data: Any,
            subscribe: bool,
        ) -> Any: ...

        def get_full_tick(self, symbols: Any) -> Any: ...

        def get_stock_list_in_sector(self, sector: Any) -> Any: ...
else:
    BridgeContextInfo = Any


class BridgeState:
    owner_id: str
    gateway_url: str
    poll_interval_seconds: int
    last_error: str
    last_poll_at: str
    started_at: str


STATE = BridgeState()
STATE.owner_id = "bigqmt-" + str(os.getpid())
STATE.gateway_url = os.environ.get("QMT_BRIDGE_GATEWAY_URL", "http://127.0.0.1:9002/qmt/bridge")
STATE.poll_interval_seconds = 1
STATE.last_error = ""
STATE.last_poll_at = ""
STATE.started_at = time.strftime("%Y-%m-%d %H:%M:%S")


def init(ContextInfo: BridgeContextInfo) -> None:
    """QMT entrypoint."""
    try:
        ContextInfo.run_time("mist_qmt_bridge_tick", "1nSecond", "2026-01-01 09:30:00")
    except Exception:
        STATE.last_error = traceback.format_exc()


def mist_qmt_bridge_tick(ContextInfo: BridgeContextInfo) -> None:
    """Poll one batch of commands and post results."""
    try:
        STATE.last_poll_at = time.strftime("%Y-%m-%d %H:%M:%S")
        _register_owner()
        poll_payload = _post_json(
            STATE.gateway_url + "/poll",
            {"ownerId": STATE.owner_id, "limit": 1},
        )
        commands_value = poll_payload.get("commands", [])
        commands = (
            cast(List[Any], commands_value) if isinstance(commands_value, list) else []
        )
        for command_value in commands:
            if not isinstance(command_value, dict):
                continue
            command = cast(Dict[str, Any], command_value)
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


def _register_owner() -> Dict[str, Any]:
    return _post_json(
        STATE.gateway_url + "/owner",
        {
            "ownerId": STATE.owner_id,
            "startedAt": STATE.started_at,
            "lastPollAt": STATE.last_poll_at,
        },
    )


def _post_json(url: str, payload: Mapping[str, Any]) -> Dict[str, Any]:
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
        parsed = json.loads(response_body)
        if isinstance(parsed, dict):
            return cast(Dict[str, Any], parsed)
        return {
            "ok": False,
            "error": {
                "code": "QMT_BRIDGE_GATEWAY_INVALID_RESPONSE",
                "message": "Gateway response is not a JSON object",
                "retryable": True,
                "details": {"url": url},
            },
        }
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


def _execute_command(ContextInfo: BridgeContextInfo, command: Mapping[str, Any]) -> Dict[str, Any]:
    method = str(command.get("method", ""))
    params_value = command.get("params", {})
    params = {}  # type: Dict[str, Any]
    if isinstance(params_value, dict):
        params = cast(Dict[str, Any], params_value)
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
                params.get("stock_list", []),
                period=params.get("period", "1d"),
                start_time=params.get("start_time", ""),
                end_time=params.get("end_time", ""),
                count=params.get("count", -1),
                dividend_type=params.get("dividend_type", "none"),
                fill_data=params.get("fill_data", True),
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
