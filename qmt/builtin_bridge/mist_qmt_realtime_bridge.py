#coding:gbk
"""Stdlib-only full-QMT realtime bridge script.

Paste or import this script from the full QMT built-in Python strategy editor.
It deliberately avoids third-party packages, threads, subprocesses, and local
socket listeners. The external Mist datasource owns concurrency; this script
polls one local command gateway and executes commands serially.
"""

import hashlib
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
    tick_count: int
    last_error: str
    last_poll_at: str
    lease_token: str
    generation: int
    started_at: str


STATE = BridgeState()
STATE.owner_id = "bigqmt-" + str(os.getpid())
STATE.gateway_url = os.environ.get("QMT_BRIDGE_GATEWAY_URL", "http://127.0.0.1:9002/qmt/bridge")
STATE.poll_interval_seconds = 1
STATE.tick_count = 0
STATE.last_error = ""
STATE.last_poll_at = ""
STATE.lease_token = ""
STATE.generation = 0

BRIDGE_BUILD_ID = "mist-qmt-realtime-bridge-v1.0"
with open(__file__, "rb") as _bridge_file:
    BRIDGE_ARTIFACT_SHA256 = hashlib.sha256(_bridge_file.read()).hexdigest()
STATE.started_at = time.strftime("%Y-%m-%d %H:%M:%S")


def init(ContextInfo: BridgeContextInfo) -> None:
    """QMT entrypoint."""
    try:
        start_time = time.strftime("%Y-%m-%d %H:%M:%S")
        STATE.started_at = start_time
        ContextInfo.run_time("mist_qmt_realtime_bridge_tick", "1nSecond", start_time)
        print(
            "mist_qmt_realtime_bridge scheduled ownerId="
            + STATE.owner_id
            + " startTime="
            + start_time
            + " gateway="
            + STATE.gateway_url
        )
    except Exception:
        STATE.last_error = traceback.format_exc()
        print("mist_qmt_realtime_bridge schedule error " + STATE.last_error)


def mist_qmt_realtime_bridge_tick(ContextInfo: BridgeContextInfo) -> None:
    """Poll one batch of commands and post results."""
    try:
        STATE.tick_count += 1
        STATE.last_poll_at = time.strftime("%Y-%m-%d %H:%M:%S")
        _register_owner()
        poll_payload = _post_json(
            STATE.gateway_url + "/poll",
            {
                "ownerId": STATE.owner_id,
                "leaseToken": STATE.lease_token,
                "generation": STATE.generation,
                "limit": 1,
            },
        )
        commands_value = poll_payload.get("commands", [])
        commands = (
            cast(List[Any], commands_value) if isinstance(commands_value, list) else []
        )
        _log_tick(len(commands))
        for command_value in commands:
            if not isinstance(command_value, dict):
                continue
            command = cast(Dict[str, Any], command_value)
            _log_command(command)
            result = _execute_command(ContextInfo, command)
            _post_json(
                STATE.gateway_url + "/result",
                {
                    "ownerId": STATE.owner_id,
                    "leaseToken": STATE.lease_token,
                    "generation": STATE.generation,
                    "commandId": command.get("commandId"),
                    "ok": result.get("ok", False),
                    "result": result.get("result"),
                    "error": result.get("error"),
                },
            )
    except Exception:
        STATE.last_error = traceback.format_exc()
        _log_tick(0)


def _register_owner() -> Dict[str, Any]:
    response = _post_json(
        STATE.gateway_url + "/owner",
        {
            "ownerId": STATE.owner_id,
            "startedAt": STATE.started_at,
            "lastPollAt": STATE.last_poll_at,
            "bridgeBuildId": BRIDGE_BUILD_ID,
            "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
        },
    )
    STATE.lease_token = str(response.get("leaseToken", ""))
    STATE.generation = int(response.get("generation", 0))
    return response


def _log_tick(command_count: int) -> None:
    if STATE.tick_count <= 5 or STATE.tick_count % 30 == 0:
        print(
            "mist_qmt_realtime_bridge tick ownerId="
            + STATE.owner_id
            + " tickCount="
            + str(STATE.tick_count)
            + " lastPollAt="
            + STATE.last_poll_at
            + " commandCount="
            + str(command_count)
            + " lastError="
            + STATE.last_error[:200]
        )


def _log_command(command: Mapping[str, Any]) -> None:
    print(
        "mist_qmt_realtime_bridge command commandId="
        + str(command.get("commandId", ""))
        + " method="
        + str(command.get("method", ""))
        + " params="
        + _short_json(command.get("params", {}))
    )


def _log_call_start(method: str, command: Mapping[str, Any], params: Mapping[str, Any]) -> None:
    print(
        "mist_qmt_realtime_bridge call_start commandId="
        + str(command.get("commandId", ""))
        + " method="
        + method
        + " params="
        + _short_json(params)
    )


def _log_call_ok(method: str, command: Mapping[str, Any]) -> None:
    print(
        "mist_qmt_realtime_bridge call_ok commandId="
        + str(command.get("commandId", ""))
        + " method="
        + method
    )


def _log_call_error(method: str, command: Mapping[str, Any], error: Any) -> None:
    print(
        "mist_qmt_realtime_bridge call_error commandId="
        + str(command.get("commandId", ""))
        + " method="
        + method
        + " error="
        + str(error)[:300]
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
            _log_call_start("get_market_data_ex", command, params)
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
            _log_call_ok("get_market_data_ex", command)
            return {"ok": True, "result": _json_safe(data)}
        if method == "get_full_tick":
            _log_call_start("get_full_tick", command, params)
            data = ContextInfo.get_full_tick(params.get("symbols", []))
            _log_call_ok("get_full_tick", command)
            return {"ok": True, "result": _json_safe(data)}
        if method == "get_stock_list_in_sector":
            _log_call_start("get_stock_list_in_sector", command, params)
            data = ContextInfo.get_stock_list_in_sector(
                params.get("sector", "\u6caa\u6df1A\u80a1")
            )
            _log_call_ok("get_stock_list_in_sector", command)
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
        _log_call_error(method, command, exc)
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


def _short_json(value: Any) -> str:
    try:
        text = json.dumps(_json_safe(value), sort_keys=True)
    except Exception:
        text = str(value)
    if len(text) > 300:
        return text[:300] + "..."
    return text
