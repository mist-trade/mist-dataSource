# coding:gbk
"""Stdlib-only full-QMT history and native-subscription bridge.

The script runs inside embedded Python 3.6. History commands keep the existing
poll/result transport. Realtime observations come only from native subscription
callbacks and are drained by the scheduled QMT runtime function.
"""

import contextlib
import datetime
import hashlib
import json
import os
import socket
import struct
import time
import traceback
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Tuple, cast

if TYPE_CHECKING:
    from typing import Protocol

    class BridgeContextInfo(Protocol):
        """Subset used by this bridge; names follow ThinkTrader ContextInfo docs."""

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

        def get_stock_list_in_sector(self, sector: Any) -> Any: ...

        def get_all_subscription(self) -> Any: ...

        def subscribe_quote(
            self,
            symbol: str,
            *,
            period: str,
            dividend_type: str,
            result_type: str,
            callback: Any,
        ) -> Any: ...

        def subscribe_whole_quote(self, symbols: Any, *, callback: Any) -> Any: ...

        def unsubscribe_quote(self, sub_id: int) -> Any: ...
else:
    BridgeContextInfo = Any


class BridgeState:
    owner_id: str
    gateway_url: str
    tick_count: int
    last_error: str
    last_poll_at: str
    lease_token: str
    generation: int
    started_at: str
    # E: persistent TCP sender + register frame (for reconnect) + counters.
    sender: Any
    register_frame: Any  # Optional[Dict] — Python 3.6 compatible
    callback_count: int
    send_dropped: int
    send_failures: int
    callback_holders: Dict[int, Dict[str, Any]]


SNAPSHOT_ITEM_MAX_BYTES = 256 * 1024
SNAPSHOT_MAX_DEPTH = 8
SNAPSHOT_MAX_COLLECTION_ITEMS = 256
BOUNDED_LOG_TEXT = 300

# E transport: persistent TCP (default) or legacy HTTP POST.
QMT_BRIDGE_TRANSPORT = os.environ.get("QMT_BRIDGE_TRANSPORT", "tcp")  # tcp|http
# Host 9004 is owned by XtItClient.exe (the QMT terminal's own local channel,
# verified 2026-08-11 via netstat on the production box), so the bridge TCP
# direct-push port defaults to 9014 (mapped to the datasource container's
# internal 9004). env override kept for experiments.
QMT_TCP_HOST = os.environ.get("QMT_TCP_HOST", "127.0.0.1")
QMT_TCP_PORT = int(os.environ.get("QMT_TCP_PORT", "9014"))
# Observability frame every N ticks (1s tick -> every 30s).
OBSERVABILITY_TICK_INTERVAL = 30

STATE = BridgeState()
STATE.owner_id = "bigqmt-" + str(os.getpid())
STATE.gateway_url = os.environ.get("QMT_BRIDGE_GATEWAY_URL", "http://127.0.0.1:9002/qmt/bridge")
STATE.tick_count = 0
STATE.last_error = ""
STATE.last_poll_at = ""
STATE.lease_token = ""
STATE.generation = 0
STATE.sender = None
STATE.register_frame = None
STATE.callback_count = 0
STATE.send_dropped = 0
STATE.send_failures = 0
STATE.callback_holders = {}

BRIDGE_BUILD_ID = "mist-qmt-realtime-bridge-v2.0"


def _compute_artifact_sha256() -> str:
    """Hash a file-backed script without requiring QMT to define ``__file__``."""
    script_path = globals().get("__file__")
    if not isinstance(script_path, str) or not script_path:
        return "unavailable"
    try:
        with open(os.path.abspath(script_path), "rb") as bridge_file:
            return hashlib.sha256(bridge_file.read()).hexdigest()
    except Exception:
        return "unavailable"


BRIDGE_ARTIFACT_SHA256 = _compute_artifact_sha256()
STATE.started_at = time.strftime("%Y-%m-%d %H:%M:%S")


def init(ContextInfo: BridgeContextInfo) -> None:
    """QMT entrypoint."""
    try:
        start_time = time.strftime("%Y-%m-%d %H:%M:%S")
        STATE.started_at = start_time
        ContextInfo.run_time("mist_qmt_realtime_bridge_tick", "1nSecond", start_time)
        _register_owner()
        _init_sender()
        _log_control(
            "build",
            0,
            "init",
            {
                "ownerId": STATE.owner_id,
                "buildId": BRIDGE_BUILD_ID,
                "artifactSha256": BRIDGE_ARTIFACT_SHA256,
            },
        )
    except Exception:
        STATE.last_error = traceback.format_exc()
        print("mist_qmt_realtime_bridge schedule error " + STATE.last_error[:BOUNDED_LOG_TEXT])


# --- persistent TCP sender (inlined: the terminal loads a single script) ---

FRAME_MAX_BYTES = 64 * 1024  # gateway native safety cap (64KiB)
RECONNECT_BACKOFF_BASE_SECONDS = 0.5
RECONNECT_BACKOFF_MAX_SECONDS = 5.0
CONNECT_TIMEOUT_SECONDS = 3.0


class SocketSender:
    """One persistent TCP connection to the datasource realtime gateway.

    Lock-free by design (owner decision, 2026-08-10): the callback context and
    the main loop / tick may race on `_sock`, but every mutation is a GIL-
    atomic attribute/dict write and a torn send surfaces as a caught OSError
    -> dropped-frame counter. latest-state semantics tolerate the loss.
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._sock = None
        self._register_payload = None
        self.reconnects = 0
        self.send_failures = 0
        self.dropped_frames = 0

    def connect(self, register_payload: dict) -> bool:
        """Open the persistent connection and send the register frame."""
        self._register_payload = register_payload
        return self._connect()

    def _connect(self) -> bool:
        self._close()
        try:
            sock = socket.create_connection(
                (self._host, self._port), timeout=CONNECT_TIMEOUT_SECONDS
            )
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = sock
            if self._register_payload is not None:
                self._send_frame(self._register_payload)
            self.reconnects += 1
            return True
        except Exception:
            self._close()
            return False

    def close(self) -> None:
        self._close()

    def _close(self) -> None:
        if self._sock is not None:
            with contextlib.suppress(Exception):
                self._sock.close()
            self._sock = None

    def send(self, frame: dict) -> bool:
        """Write one frame — non-blocking semantics for callback contexts.

        A broken connection (or a race with a reconnect) drops the frame with
        a counter; the main loop / tick reconnects. Never blocks on connect.
        """
        if self._sock is None:
            self.dropped_frames += 1
            return False
        try:
            self._send_frame(frame)
            return True
        except Exception:
            self.send_failures += 1
            self._close()
            self.dropped_frames += 1
            return False

    def reconnect_if_needed(self, _register_payload: dict) -> bool:
        """Reconnect when the socket is gone. Main-loop/tick context only."""
        if self._sock is None:
            return self._connect()
        return True

    def snapshot(self) -> dict:
        return {
            "connected": self._sock is not None,
            "reconnects": self.reconnects,
            "sendFailures": self.send_failures,
            "droppedFrames": self.dropped_frames,
        }

    def _send_frame(self, frame: dict) -> None:
        data = json.dumps(frame, separators=(",", ":")).encode("utf-8")
        if len(data) > FRAME_MAX_BYTES:
            raise ValueError(f"frame exceeds {FRAME_MAX_BYTES} bytes")
        header = struct.pack(">I", len(data))
        if self._sock is None:
            raise OSError("not connected")
        self._sock.sendall(header + data)


def _init_sender() -> None:
    """E: open the persistent TCP connection and register (best effort)."""
    if QMT_BRIDGE_TRANSPORT != "tcp":
        return
    try:
        STATE.sender = SocketSender(QMT_TCP_HOST, QMT_TCP_PORT)
        STATE.register_frame = {
            "type": "register",
            "provider": "qmt",
            "ownerId": STATE.owner_id,
            "leaseToken": STATE.lease_token,
            "generation": STATE.generation,
            "bridgeBuildId": BRIDGE_BUILD_ID,
            "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
        }
        STATE.sender.connect(STATE.register_frame)
    except Exception as exc:
        # Sender is optional: a failure falls back to the HTTP transport.
        # Not recorded in STATE.last_error (that is reserved for fatal paths).
        print("mist_qmt_realtime_bridge sender init error " + str(exc))


def mist_qmt_realtime_bridge_tick(ContextInfo: BridgeContextInfo) -> None:
    """Poll history/control once and reconnect/push via the sender."""
    try:
        STATE.tick_count += 1
        STATE.last_poll_at = time.strftime("%Y-%m-%d %H:%M:%S")
        if not STATE.lease_token:
            _register_owner()
        history_count = _poll_history(ContextInfo)
        control_count = _poll_subscription_control(ContextInfo)
        if STATE.sender is not None and STATE.register_frame is not None:
            STATE.sender.reconnect_if_needed(STATE.register_frame)
        if STATE.tick_count % OBSERVABILITY_TICK_INTERVAL == 0:
            _send_observability(STATE.owner_id, STATE.lease_token, STATE.generation, STATE.sender)
        _log_tick(history_count, control_count, 0)
    except Exception:
        STATE.last_error = traceback.format_exc()
        _log_tick(0, 0, 0)


def _send_observability(owner_id: str, lease_token: str, generation: int, sender: Any) -> None:
    """Push bridge counters to the datasource observability endpoint (E-0).

    Parameter-style signature mirrors the TDX bridge. Observability loss is
    acceptable — never raise.
    """
    try:
        payload = {
            "ownerId": owner_id,
            "leaseToken": lease_token,
            "generation": generation,
            "intervalSeconds": float(OBSERVABILITY_TICK_INTERVAL),
            "counters": {
                "callback_count": STATE.callback_count,
                "send_dropped": STATE.send_dropped,
                "send_failures": STATE.send_failures,
            },
            "sender": sender.snapshot() if sender is not None else None,
        }
        _post_json(STATE.gateway_url + "/observability", payload)
    except Exception:
        pass  # observability loss is acceptable


def _poll_history(ContextInfo: BridgeContextInfo) -> int:
    poll_payload = _post_json(
        STATE.gateway_url + "/poll",
        {
            "ownerId": STATE.owner_id,
            "leaseToken": STATE.lease_token,
            "generation": STATE.generation,
            "limit": 1,
        },
    )
    if _lease_rejected(poll_payload):
        STATE.lease_token = ""
        return 0
    commands_value = poll_payload.get("commands", [])
    commands = cast(List[Any], commands_value) if isinstance(commands_value, list) else []
    count = 0
    for command_value in commands:
        if not isinstance(command_value, dict):
            continue
        command = cast(Dict[str, Any], command_value)
        _log_command(command)
        result = _execute_history_command(ContextInfo, command)
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
        count += 1
    return count


def _poll_subscription_control(ContextInfo: BridgeContextInfo) -> int:
    poll_payload = _post_json(
        STATE.gateway_url + "/subscriptions/poll",
        {
            "ownerId": STATE.owner_id,
            "leaseToken": STATE.lease_token,
            "generation": STATE.generation,
        },
    )
    if _lease_rejected(poll_payload):
        STATE.lease_token = ""
        return 0
    command_value = poll_payload.get("command")
    if command_value is None:
        return 0
    if not isinstance(command_value, dict):
        _bounded_diagnostic("invalid_control_command", "command is not an object")
        return 0
    command = cast(Dict[str, Any], command_value)
    result = _execute_subscription_command(ContextInfo, command)
    payload = {
        "ownerId": STATE.owner_id,
        "leaseToken": STATE.lease_token,
        "generation": STATE.generation,
        "callSequence": command.get("callSequence"),
    }  # type: Dict[str, Any]
    if "success" in result:
        payload["success"] = result.get("success")
    else:
        payload["failure"] = result.get("failure")
    post_result = _post_json(STATE.gateway_url + "/subscriptions/result", payload)
    if _lease_rejected(post_result):
        STATE.lease_token = ""
    return 1


def _register_owner() -> Dict[str, Any]:
    response = _post_json(
        STATE.gateway_url + "/owner",
        {
            "ownerId": STATE.owner_id,
            "startedAt": STATE.started_at,
            "lastPollAt": STATE.last_poll_at,
            "bridgeBuildId": BRIDGE_BUILD_ID,
            "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
            "bridgeRuntimeFingerprint": _compute_runtime_fingerprint(),
        },
    )
    token = response.get("leaseToken")
    generation = response.get("generation")
    if isinstance(token, str) and type(generation) is int and generation > 0:
        STATE.lease_token = token
        STATE.generation = generation
        STATE.last_error = ""
    return response


def _execute_subscription_command(
    ContextInfo: BridgeContextInfo,
    command: Mapping[str, Any],
) -> Dict[str, Any]:
    sequence = command.get("callSequence")
    method = command.get("method")
    if type(sequence) is not int or sequence <= 0:
        return _native_failure(None, "QMT_NATIVE_CALL_SEQUENCE_INVALID")
    if not isinstance(method, str):
        return _native_failure(None, "QMT_NATIVE_METHOD_INVALID")
    expected_keys = {
        "subscribe_quote": {"callSequence", "method", "symbol"},
        "subscribe_whole_quote": {"callSequence", "method", "symbols"},
        "unsubscribe_quote": {"callSequence", "method", "subId", "symbol"},
    }
    allowed = expected_keys.get(method)
    if allowed is None or set(command) != allowed:
        return _native_failure(_command_symbol(command), "QMT_NATIVE_COMMAND_INVALID")
    _log_control("intent", sequence, method, {"symbol": _command_symbol(command)})
    try:
        native_method = getattr(ContextInfo, method, None)
        if not callable(native_method):
            return _native_failure(_command_symbol(command), "QMT_NATIVE_METHOD_MISSING")
        if method == "subscribe_quote":
            symbol = command.get("symbol")
            if not isinstance(symbol, str):
                return _native_failure(None, "QMT_NATIVE_COMMAND_INVALID")
            holder = _new_callback_holder()
            callback = _make_subscription_callback(holder)
            raw_result = native_method(
                symbol,
                period="tick",
                dividend_type="none",
                result_type="dict",
                callback=callback,
            )
            _activate_callback_holder(holder, raw_result)
        elif method == "subscribe_whole_quote":
            symbols = command.get("symbols")
            if not isinstance(symbols, list) or not all(isinstance(item, str) for item in symbols):
                return _native_failure(None, "QMT_NATIVE_COMMAND_INVALID")
            holder = _new_callback_holder()
            callback = _make_subscription_callback(holder)
            raw_result = native_method(list(symbols), callback=callback)
            _activate_callback_holder(holder, raw_result)
        else:
            sub_id = command.get("subId")
            if type(sub_id) is not int:
                return _native_failure(_command_symbol(command), "QMT_NATIVE_COMMAND_INVALID")
            raw_result = native_method(sub_id)
        safe, copied = _safe_native_result(raw_result)
        if not safe:
            result = _native_failure(_command_symbol(command), "QMT_NATIVE_RESULT_UNSAFE")
        else:
            result = {"success": copied}
        _log_control(
            "result",
            sequence,
            method,
            {
                "ok": "success" in result,
                "resultType": type(raw_result).__name__,
                "result": copied if isinstance(copied, (int, float, str, bool)) else None,
            },
        )
        return result
    except Exception as exc:
        _log_control(
            "result",
            sequence,
            method,
            {"ok": False, "error": str(exc)[:BOUNDED_LOG_TEXT]},
        )
        return _native_failure(_command_symbol(command), "QMT_NATIVE_CALL_FAILED")


def _new_callback_holder() -> Dict[str, Any]:
    return {"active": True, "subscriptionId": None}


def _activate_callback_holder(holder: Dict[str, Any], raw_result: Any) -> None:
    if type(raw_result) is int:
        holder["subscriptionId"] = raw_result
        STATE.callback_holders[raw_result] = holder


def _make_subscription_callback(holder: Dict[str, Any]) -> Any:
    def callback(native_value: Any) -> None:
        try:
            if not holder.get("active", False):
                return
            subscription_id = holder.get("subscriptionId")
            if type(subscription_id) is not int:
                return
            accepted = _prepare_callback_native(native_value)
            if accepted is not None:
                _push_snapshot(
                    subscription_id,
                    datetime.datetime.now().astimezone().isoformat(),
                    accepted,
                )
        except Exception as exc:
            _bounded_diagnostic("callback_error", str(exc))

    return callback


def _prepare_callback_native(native_value: Any) -> Any:
    """Validate/bound a callback payload (provider-specific: QMT carries data).

    Returns the accepted multi-symbol map, or None when nothing is usable.
    """
    if not isinstance(native_value, dict):
        _bounded_diagnostic("callback_invalid", "native callback is not an object")
        return None
    accepted = {}  # type: Dict[str, Any]
    native_map = cast(Mapping[Any, Any], native_value)
    for raw_symbol, raw_entry in list(native_map.items())[:SNAPSHOT_MAX_COLLECTION_ITEMS]:
        symbol = str(raw_symbol).strip().upper()
        if not symbol:
            continue
        try:
            copied = _bounded_copy(raw_entry, 0)
            encoded_entry = json.dumps(
                {symbol: copied}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            if len(encoded_entry) > SNAPSHOT_ITEM_MAX_BYTES:
                raise ValueError("callback entry exceeds byte limit")
            accepted[symbol] = copied
        except Exception as exc:
            _bounded_diagnostic("callback_entry_dropped", symbol + ": " + str(exc))
    if not accepted:
        return None
    return accepted


def _push_snapshot(subscription_id: int, captured_at: str, native: Any) -> None:
    """Push one snapshot over the active transport (mirrors the TDX bridge).

    send() is non-blocking in callback contexts; a broken connection drops
    the frame with a counter and the 1s tick reconnects. HTTP fallback posts
    inline (keep-alive-free urllib; acceptable for the fallback path).
    """
    payload = {
        "ownerId": STATE.owner_id,
        "leaseToken": STATE.lease_token,
        "generation": STATE.generation,
        "subscriptionId": subscription_id,
        "capturedAt": captured_at,
        "native": native,
    }
    STATE.callback_count += 1
    if QMT_BRIDGE_TRANSPORT == "tcp":
        if STATE.sender is not None:
            frame = {"type": "snapshot"}
            frame.update(payload)
            if not STATE.sender.send(frame):
                STATE.send_dropped += 1
        else:
            STATE.send_dropped += 1
    else:
        try:
            response = _post_json(STATE.gateway_url + "/subscriptions/snapshot", payload)
            if _lease_rejected(response):
                STATE.lease_token = ""
        except Exception:
            STATE.send_dropped += 1


def _bounded_copy(value: Any, depth: int) -> Any:
    if depth > SNAPSHOT_MAX_DEPTH:
        raise ValueError("native value exceeds depth limit")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("native value contains non-finite number")
        return value
    if isinstance(value, dict):
        mapping = cast(Mapping[Any, Any], value)
        if len(mapping) > SNAPSHOT_MAX_COLLECTION_ITEMS:
            raise ValueError("native object exceeds item limit")
        result = {}  # type: Dict[str, Any]
        for key, item in mapping.items():
            result[str(key)] = _bounded_copy(item, depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        sequence = cast(Any, value)
        if len(sequence) > SNAPSHOT_MAX_COLLECTION_ITEMS:
            raise ValueError("native list exceeds item limit")
        return [_bounded_copy(item, depth + 1) for item in sequence]
    raise ValueError("native value is not JSON-safe")


def _safe_native_result(value: Any) -> Tuple[bool, Any]:
    try:
        copied = _bounded_copy(value, 0)
        json.dumps(copied)
        return True, copied
    except Exception:
        return False, None


def _native_failure(symbol: Any, reason: str) -> Dict[str, Any]:
    return {
        "failure": {
            "symbol": symbol if isinstance(symbol, str) else None,
            "reason": reason,
        }
    }


def _command_symbol(command: Mapping[str, Any]) -> Any:
    return command.get("symbol") if isinstance(command.get("symbol"), str) else None


def _execute_history_command(
    ContextInfo: BridgeContextInfo,
    command: Mapping[str, Any],
) -> Dict[str, Any]:
    method = str(command.get("method", ""))
    params_value = command.get("params", {})
    params = cast(Dict[str, Any], params_value) if isinstance(params_value, dict) else {}
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
        if method == "runtime_introspection":
            return {
                "ok": True,
                "result": _runtime_introspection(ContextInfo),
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
            return {"ok": True, "result": _history_json_safe(data)}
        if method == "get_stock_list_in_sector":
            _log_call_start("get_stock_list_in_sector", command, params)
            data = ContextInfo.get_stock_list_in_sector(params.get("sector", "\u6caa\u6df1A\u80a1"))
            _log_call_ok("get_stock_list_in_sector", command)
            return {"ok": True, "result": _history_json_safe(data)}
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


def _compute_runtime_fingerprint() -> str:
    """Fingerprint selected loaded functions without requiring ``__file__``."""
    digest = hashlib.sha256()
    names = [
        "init",
        "mist_qmt_realtime_bridge_tick",
        "_execute_subscription_command",
        "_make_subscription_callback",
        "_drain_snapshot_queue",
        "_execute_history_command",
    ]
    for name in names:
        function = globals().get(name)
        code = getattr(function, "__code__", None)
        digest.update(name.encode("utf-8"))
        if code is None:
            digest.update(b":missing")
            continue
        digest.update(code.co_code)
        digest.update(repr(code.co_consts).encode("utf-8", "backslashreplace"))
        digest.update(repr(code.co_names).encode("utf-8", "backslashreplace"))
    return digest.hexdigest()


def _runtime_introspection(ContextInfo: BridgeContextInfo) -> Dict[str, Any]:
    """Return bounded, read-only runtime identity and native method metadata."""
    methods = {}  # type: Dict[str, Any]
    for name in [
        "subscribe_quote",
        "subscribe_whole_quote",
        "unsubscribe_quote",
        "get_all_subscription",
        "get_market_data_ex",
    ]:
        candidate = getattr(ContextInfo, name, None)
        doc = getattr(candidate, "__doc__", None)
        methods[name] = {
            "available": callable(candidate),
            "type": type(candidate).__name__ if candidate is not None else "missing",
            "doc": str(doc)[:BOUNDED_LOG_TEXT] if doc else None,
        }
    active_subscription_observation = {
        "available": False,
        "ok": False,
        "result": None,
        "error": None,
    }  # type: Dict[str, Any]
    active_subscription_method = getattr(ContextInfo, "get_all_subscription", None)
    if callable(active_subscription_method):
        active_subscription_observation["available"] = True
        try:
            raw_active_subscriptions = active_subscription_method()
            safe, copied = _safe_native_result(_history_json_safe(raw_active_subscriptions))
            if safe:
                active_subscription_observation["ok"] = True
                active_subscription_observation["result"] = copied
            else:
                active_subscription_observation["error"] = "QMT_ACTIVE_SUBSCRIPTIONS_UNSAFE"
        except Exception as exc:
            active_subscription_observation["error"] = str(exc)[:BOUNDED_LOG_TEXT]
    return {
        "bridgeBuildId": BRIDGE_BUILD_ID,
        "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
        "bridgeRuntimeFingerprint": _compute_runtime_fingerprint(),
        "ownerId": STATE.owner_id,
        "startedAt": STATE.started_at,
        "pythonVersion": ".".join(str(item) for item in __import__("sys").version_info[:3]),
        "contextType": type(ContextInfo).__name__,
        "methods": methods,
        "activeSubscriptionObservation": active_subscription_observation,
    }


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
        return cast(Dict[str, Any], parsed) if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        return {"_httpStatus": exc.code, "_error": str(exc)[:BOUNDED_LOG_TEXT]}
    except urllib.error.URLError as exc:
        return {"_httpStatus": 0, "_error": str(exc)[:BOUNDED_LOG_TEXT]}


def _lease_rejected(response: Mapping[str, Any]) -> bool:
    return response.get("_httpStatus") in (401, 403, 409)


def _log_tick(history_count: int, control_count: int, drained_count: int) -> None:
    if STATE.tick_count <= 5 or STATE.tick_count % 30 == 0:
        print(
            "mist_qmt_realtime_bridge tick ownerId="
            + STATE.owner_id
            + " tickCount="
            + str(STATE.tick_count)
            + " historyCommandCount="
            + str(history_count)
            + " controlCommandCount="
            + str(control_count)
            + " snapshotDrainCount="
            + str(drained_count)
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


def _log_call_start(
    method: str,
    command: Mapping[str, Any],
    params: Mapping[str, Any],
) -> None:
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
        + str(error)[:BOUNDED_LOG_TEXT]
    )


def _log_control(
    event: str,
    sequence: int,
    method: str,
    detail: Mapping[str, Any],
) -> None:
    record = {
        "event": event,
        "callSequence": sequence,
        "method": method,
        "detail": detail,
        "buildId": BRIDGE_BUILD_ID,
        "timestamp": datetime.datetime.now().astimezone().isoformat(),
    }
    print("mist_qmt_realtime_bridge control " + _short_json(record))


def _bounded_diagnostic(event: str, reason: str) -> None:
    print("mist_qmt_realtime_bridge " + event[:80] + " reason=" + str(reason)[:BOUNDED_LOG_TEXT])


def _history_json_safe(value: Any) -> Any:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    if isinstance(value, dict):
        result = {}  # type: Dict[str, Any]
        mapping = cast(Mapping[Any, Any], value)
        for key, item in mapping.items():
            result[str(key)] = _history_json_safe(item)
        return result
    if isinstance(value, (list, tuple)):
        sequence = cast(Any, value)
        return [_history_json_safe(item) for item in sequence]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _short_json(value: Any) -> str:
    try:
        text = json.dumps(_history_json_safe(value), sort_keys=True)
    except Exception:
        text = str(value)
    if len(text) > BOUNDED_LOG_TEXT:
        return text[:BOUNDED_LOG_TEXT] + "..."
    return text
