#!/usr/bin/env python3
"""mist_tdx_realtime_bridge.py — TDX terminal builtin bridge strategy script.

Runs INSIDE the TDX terminal's tqcenter Python environment (Python 3.7 +
stdlib + tqcenter only). Communicates with the datasource realtime gateway
over loopback HTTP.

Design invariants (frozen in C0.1):
- subscribe_hq callback ONLY marks symbols dirty (under threading.Lock, no
  SDK/HTTP calls in callback).
- Worker/poll loop: reconcile subscriptions, fetch get_market_snapshot for
  dirty symbols, POST native projection to gateway.
- Snapshot POST is attempted once; latest-state observations are never replayed.
- Carries bridgeBuildId + bridgeArtifactSha256 in owner registration.

Environment:
- tqcenter.tq available (subscribe_hq, unsubscribe_hq, get_market_snapshot,
  initialize, get_subscribe_hq_stock_list)
- stdlib only (urllib, json, threading, time, hashlib, os)

Manual operator actions: load in TQ strategy manager, start/stop/delete.
HIL required to verify on target Windows/TDX build.

This file is a versioned deliverable. Build ID and artifact SHA are reported
to the gateway at registration time and surfaced in health.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import socket
import struct
import time
import urllib.error
import urllib.request
from collections import deque

# --- Configuration ----------------------------------------------------

DATASOURCE_URL = os.environ.get("MIST_DATASOURCE_URL", "http://127.0.0.1:9001")
BRIDGE_ENDPOINT = DATASOURCE_URL.rstrip("/") + "/tdx/bridge"
POLL_INTERVAL_SECONDS = 3.0
NATIVE_KEEPALIVE_INTERVAL_SECONDS = 30.0
HTTP_TIMEOUT_SECONDS = 2.0
RETRY_BASE_SECONDS = 0.25
RETRY_MAX_SECONDS = 5.0
RECONCILE_BATCH = 50
BRIDGE_QUEUE_MAX = 1000
BRIDGE_QUEUE: deque[str] = deque(maxlen=BRIDGE_QUEUE_MAX)  # thin callback → main-thread drain

OBSERVABILITY_INTERVAL_SECONDS = 30.0

# Stall-confirmed re-arm (spec realtime-subscription-restart-recovery R3).
# Off by default: enables unsubscribe+subscribe force re-arm when the datasource
# keeps re-issuing the full desired list (PUSHING) but callbacks are not
# advancing — i.e. `subscribe_hq` on an already-listed symbol was a no-op
# (suspected from the 2026-08-14 incident). Enabled only after terminal HIL
# confirms the no-op semantics. Cooldown avoids a per-poll hot re-arm loop.
REARM_ENABLED = os.environ.get("REARM_ENABLED", "false").strip().lower() == "true"
REARM_MIN_INTERVAL_SECONDS = 30.0

# E transport: persistent TCP (default) or legacy HTTP POST.
MIST_TDX_TRANSPORT = os.environ.get("MIST_TDX_TRANSPORT", "tcp")  # tcp|http
# Quote API used inside the callback. market_snapshot is the only terminal-tested
# path: full_tick returned fetch_none on 10/10 callbacks 2026-08-11 (the tdxquant
# SDK has no get_full_tick; the plan-B example that used it is a QMT example).
# The dead get_full_tick branch was removed; get_quote() now always resolves to
# get_market_snapshot.
MIST_TDX_TCP_HOST = os.environ.get("MIST_TDX_TCP_HOST", "127.0.0.1")
MIST_TDX_TCP_PORT = int(os.environ.get("MIST_TDX_TCP_PORT", "9003"))


# Contract tuple (must match gateway ACCEPTED_* constants).
ACQUISITION_PROFILE = "tdx.get_market_snapshot"
SCHEMA_VERSION = 2

# Bounded diagnostic text length (aligns with QMT bridge).
BOUNDED_LOG_TEXT = 300

# Build identity (computed at load time).
BRIDGE_BUILD_ID = "mist-tdx-realtime-bridge-v3.1"


def _resolve_script_path():
    """Return the terminal script path when the host exposes file semantics."""
    script_path = globals().get("__file__")
    if not isinstance(script_path, str) or not script_path:
        return None
    return os.path.abspath(script_path)


BRIDGE_SCRIPT_PATH = _resolve_script_path()


def _compute_artifact_sha256() -> str:
    """Compute SHA256 when the terminal exposes a file-backed script."""
    if BRIDGE_SCRIPT_PATH is None:
        return "unavailable"
    try:
        with open(BRIDGE_SCRIPT_PATH, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return "unavailable"


BRIDGE_ARTIFACT_SHA256 = _compute_artifact_sha256()

OWNER_FENCE_CODES = {
    "TDX_BRIDGE_NO_OWNER",
}
OWNER_REPLACED_CODES = {
    "TDX_BRIDGE_LEASE_INVALID",
    "TDX_BRIDGE_EPOCH_MISMATCH",
    "TDX_BRIDGE_OWNER_RETIRED",
}


# --- HTTP helpers (stdlib only) ---------------------------------------


def _post_json(url: str, payload: dict) -> dict:
    """POST JSON to gateway, return parsed response. Raises on network error."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _retry_delay_seconds(response: dict | None, attempt: int) -> float:
    """Return a bounded delay, preferring the gateway classification."""
    retry_after_ms = response.get("retryAfterMs") if isinstance(response, dict) else None
    if isinstance(retry_after_ms, (int, float)) and retry_after_ms >= 0:
        return min(float(retry_after_ms) / 1000.0, RETRY_MAX_SECONDS)
    return min(RETRY_BASE_SECONDS * (2 ** max(0, attempt - 1)), RETRY_MAX_SECONDS)


def _requires_registration(error: dict) -> bool:
    return error.get("code") in OWNER_FENCE_CODES


def _owner_was_replaced(error: dict) -> bool:
    return error.get("code") in OWNER_REPLACED_CODES


# --- Dirty symbol queue (thread-safe) ---------------------------------


class BridgeOwner:
    """Tracks lease + epoch state from gateway registration."""

    def __init__(self) -> None:
        self.lease_token: str | None = None
        self.stream_epoch: str | None = None
        self.owner_id: str = f"tdx-bridge-pid-{os.getpid()}"
        self.applied_revision: int = -1
        self._active_native: set[str] = set()
        self.registration_retry_seconds: float = POLL_INTERVAL_SECONDS
        self._last_registration_error_code: str | None = None
        self.last_native_probe_monotonic: float = 0.0
        self.last_attempted_revision: int = -1
        self.last_native_probe_revision: int = 0

    def registration_payload(self) -> dict:
        return {
            "ownerId": self.owner_id,
            "mode": "builtin",
            "bridgeBuildId": BRIDGE_BUILD_ID,
            "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
            "acquisitionProfile": ACQUISITION_PROFILE,
            "schemaVersion": SCHEMA_VERSION,
        }

    def request_identity(self) -> dict:
        """Return the generation-fenced identity required after registration."""
        if self.lease_token is None or self.stream_epoch is None:
            raise RuntimeError("bridge owner is not registered")
        return {
            "leaseToken": self.lease_token,
            "streamEpoch": self.stream_epoch,
        }

    def register(self) -> bool:
        """Register with gateway. Returns True on success."""
        resp = _post_json(
            BRIDGE_ENDPOINT + "/owner",
            self.registration_payload(),
        )
        if "leaseToken" not in resp:
            error = resp.get("error", {})
            self.registration_retry_seconds = _retry_delay_seconds(error, 1)
            error_code = error.get("code", "unknown")
            if error_code != self._last_registration_error_code:
                if error_code == "TDX_BRIDGE_OWNER_ACTIVE":
                    print(
                        "[mist-bridge] previous owner is still active; waiting for bounded takeover"
                    )
                else:
                    print(f"[mist-bridge] registration failed: {resp}")
            self._last_registration_error_code = error_code
            return False
        self.lease_token = resp["leaseToken"]
        self.stream_epoch = resp.get("streamEpoch")
        self.applied_revision = -1
        self._active_native = set()
        self.last_native_probe_monotonic = 0.0
        self.last_attempted_revision = -1
        self.last_native_probe_revision = 0
        self.registration_retry_seconds = POLL_INTERVAL_SECONDS
        self._last_registration_error_code = None
        # Do NOT log lease token (even partial) — per golden contract.
        print(f"[mist-bridge] registered: epoch={self.stream_epoch} build={BRIDGE_BUILD_ID}")
        return True


# --- tqcenter wrapper -------------------------------------------------


class TqCenterWrapper:
    """Wrap the real tqcenter.tq SDK and fail closed when it is unavailable."""

    def __init__(self) -> None:
        self._tq = None

    def initialize(self) -> None:
        try:
            from tqcenter import tq  # type: ignore[import-not-found]

            if BRIDGE_SCRIPT_PATH is None:
                raise SystemExit(
                    "[mist-bridge] FATAL: TDX did not expose a file-backed strategy path."
                    " Register mist_tdx_realtime_bridge.py from PYPlugins/user instead of"
                    " pasting it into a pathless execution context."
                )
            tq.initialize(BRIDGE_SCRIPT_PATH)
            self._tq = tq
            print("[mist-bridge] tqcenter initialized (real SDK)")
        except ImportError as exc:
            raise SystemExit(
                "[mist-bridge] FATAL: tqcenter not available."
                f" This script must run inside the TDX terminal. Import error: {exc}"
            ) from exc

    def subscribe_hq(self, codes: list[str], callback) -> None:
        self._tq.subscribe_hq(codes, callback)

    def unsubscribe_hq(self, codes: list[str]) -> None:
        self._tq.unsubscribe_hq(codes)

    def get_market_snapshot(self, code: str) -> dict | None:
        try:
            result = self._tq.get_market_snapshot(code)
            if isinstance(result, str):
                return json.loads(result)
            return result
        except Exception as e:
            print(f"[mist-bridge] get_market_snapshot error for {code}: {e}")
            return None

    def get_quote(self, code: str) -> dict | None:
        """Quote source used inside the callback. market_snapshot only —
        get_full_tick is a QMT method, not present on the tdxquant SDK."""
        return self.get_market_snapshot(code)

    def get_subscribe_hq_stock_list(self) -> list[str]:
        result = self._tq.get_subscribe_hq_stock_list()
        if isinstance(result, str):
            result = json.loads(result)
        if result is None:
            return []
        if not isinstance(result, list) or not all(isinstance(item, str) for item in result):
            raise TypeError("get_subscribe_hq_stock_list must return a list of strings")
        return result


# --- Main bridge loop -------------------------------------------------


def _format_code(raw: str) -> str:
    """Normalize to suffix format (e.g. SH600519 → 600519.SH)."""
    raw = raw.strip().upper()
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) == 8:
        return raw[2:] + "." + raw[:2]
    return raw


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

    def reconnect_if_needed(self, register_payload: dict) -> bool:
        """Reconnect when the socket is gone. Main-loop/tick context only.

        The caller rebuilds the register frame from the CURRENT owner identity
        before each reconnect; store it so _connect() registers with the fresh
        lease (a stale startup frame is rejected after a datasource restart).
        """
        if self._sock is None:
            self._register_payload = register_payload
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


def _make_register_frame(owner: BridgeOwner) -> dict:
    """Build the TCP register frame with the owner's CURRENT lease identity.

    The lease/epoch pair is refreshed on every reconnect: a re-registration
    (lease lost / datasource restart) issues a new lease, and a stale frame
    would be rejected by the gateway's owner validator forever.
    """
    return {
        "type": "register",
        "provider": "tdx",
        **owner.request_identity(),
        "bridgeBuildId": BRIDGE_BUILD_ID,
        "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
        "acquisitionProfile": ACQUISITION_PROFILE,
        "schemaVersion": SCHEMA_VERSION,
    }


def _init_sender(owner: BridgeOwner):
    """E: open the persistent TCP connection and register (best effort)."""
    if MIST_TDX_TRANSPORT != "tcp":
        return None, None
    sender = SocketSender(MIST_TDX_TCP_HOST, MIST_TDX_TCP_PORT)
    register_frame = _make_register_frame(owner)
    if not sender.connect(register_frame):
        print("[mist-bridge] TCP connect failed; reconnecting in main loop")
    return sender, register_frame


def _bounded_diagnostic(event: str, reason: str) -> None:
    print("[mist-bridge] " + event[:80] + " reason=" + str(reason)[:BOUNDED_LOG_TEXT])


def _make_subscription_callback(counters: dict):
    """Subscribe callback: append the changed code to BRIDGE_QUEUE (thin).

    C0.1 invariant: the callback makes no SDK calls and no transport send.
    The main loop owns all fetch + push by draining the queue.
    """

    def on_quote_update(data_str: str) -> None:
        try:
            data = json.loads(data_str)
            code = data.get("Code")
            if code:
                code = _format_code(code)
                BRIDGE_QUEUE.append(code)  # GIL-atomic; thin
                counters["callback_count"] += 1
        except Exception as exc:
            # Bounded diagnostic (aligns with QMT bridge): callback errors must
            # never raise, but must never be silent either (F4-q).
            _bounded_diagnostic("callback_error", str(exc))

    return on_quote_update


def _drain_bridge_queue(
    tq_wrapper: TqCenterWrapper, owner: BridgeOwner, sender, counters: dict
) -> int:
    """Main-thread: drain BRIDGE_QUEUE → fetch + push. Returns drained count."""
    drained = 0
    while BRIDGE_QUEUE:
        code = BRIDGE_QUEUE.popleft()
        native = tq_wrapper.get_quote(code)
        if native is None:
            counters["fetch_none"] += 1
            continue
        counters["fetch_count"] += 1
        captured_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
        captured_at += _tz_offset_suffix()
        _push_snapshot(owner, sender, counters, code, captured_at, native)
        drained += 1
    return drained


def _push_snapshot(
    owner: BridgeOwner, sender, counters: dict, code: str, captured_at: str, native: dict
) -> None:
    """Push one snapshot over the active transport (mirrors the QMT bridge).

    send() is non-blocking in callback contexts; a broken connection drops
    the frame with a counter and the main loop reconnects.
    """
    if MIST_TDX_TRANSPORT == "tcp":
        if not sender.send(
            {
                "type": "snapshot",
                "symbol": code,
                "capturedAt": captured_at,
                "native": native,
            }
        ):
            counters["send_dropped"] += 1
    else:
        try:
            _post_json(
                BRIDGE_ENDPOINT + "/snapshot",
                {
                    **owner.request_identity(),
                    "symbol": code,
                    "capturedAt": captured_at,
                    "native": native,
                },
            )
        except urllib.error.URLError:
            counters["send_dropped"] += 1


def _send_observability(owner: BridgeOwner, sender, counters: dict) -> None:
    """Push bridge-side counters to the datasource observability endpoint.

    The bridge has no OTel SDK (terminal stdlib-only); counters ride the
    existing HTTP path and become OTel metrics on the datasource side.
    Observability loss is acceptable — never raise.
    """
    try:
        body = {
            **owner.request_identity(),
            "intervalSeconds": OBSERVABILITY_INTERVAL_SECONDS,
            "counters": dict(counters),
            "sender": sender.snapshot() if sender is not None else None,
        }
        _post_json(BRIDGE_ENDPOINT + "/observability", body)
    except Exception:
        pass


def _register_owner(owner: BridgeOwner) -> None:
    """Register with gateway (retry on network error)."""
    while True:
        try:
            if owner.register():
                return
        except Exception as e:
            print(f"[mist-bridge] registration error: {e}")
        time.sleep(owner.registration_retry_seconds)


def run_bridge() -> None:
    """Main bridge loop. Registers, reconciles subscriptions, pushes quotes."""
    _bounded_diagnostic(
        "bridge_start",
        (
            f"pid={os.getpid()} parentPid={os.getppid()} "
            f"startedAt={time.strftime('%Y-%m-%dT%H:%M:%S')} "
            f"transport={MIST_TDX_TRANSPORT} build={BRIDGE_BUILD_ID} "
            f"rearmEnabled={REARM_ENABLED}"
        ),
    )
    tq_wrapper = TqCenterWrapper()
    tq_wrapper.initialize()

    owner = BridgeOwner()
    _register_owner(owner)

    sender, register_frame = _init_sender(owner)

    counters = {
        "callback_count": 0,
        "fetch_count": 0,
        "fetch_none": 0,
        "send_dropped": 0,
    }
    last_obs_at = time.monotonic()
    quote_callback = _make_subscription_callback(counters)
    # Stall-confirmed re-arm bookkeeping (only when REARM_ENABLED).
    last_rearm_cb_count: int | None = None
    last_rearm_at = 0.0

    print("[mist-bridge] starting main loop")
    while True:
        try:
            # 0. Reconnect a broken TCP connection (never inside a callback).
            #    Refresh the register frame from the CURRENT lease: after a
            #    datasource restart or a lease re-registration the gateway
            #    owner changes, and a stale frame is rejected forever.
            if MIST_TDX_TRANSPORT == "tcp":
                register_frame = _make_register_frame(owner)
                sender.reconnect_if_needed(register_frame)
                _drain_bridge_queue(tq_wrapper, owner, sender, counters)
                now = time.monotonic()
                if now - last_obs_at >= OBSERVABILITY_INTERVAL_SECONDS:
                    _send_observability(owner, sender, counters)
                    last_obs_at = now

            # 1. Poll desired state.
            poll_resp = _post_json(
                BRIDGE_ENDPOINT + "/poll",
                {
                    **owner.request_identity(),
                    "appliedRevision": owner.applied_revision,
                },
            )
            if "error" in poll_resp:
                err = poll_resp["error"]
                if _owner_was_replaced(err):
                    print("[mist-bridge] replaced by a newer bridge instance; exiting")
                    return
                if _requires_registration(err):
                    print("[mist-bridge] lease lost, re-registering...")
                    while not owner.register():
                        time.sleep(_retry_delay_seconds(err, 1))
                    continue
                print(f"[mist-bridge] poll error: {err}")
                if err.get("retryable"):
                    time.sleep(_retry_delay_seconds(err, 1))
                else:
                    time.sleep(POLL_INTERVAL_SECONDS)
                continue

            poll_retry_after = poll_resp.get("retryAfterMs", 0)
            if isinstance(poll_retry_after, (int, float)) and poll_retry_after > 0:
                time.sleep(_retry_delay_seconds(poll_resp, 1))

            desired_revision = poll_resp.get("desiredRevision", 0)
            native_probe_revision = poll_resp.get("nativeProbeRevision", 0)
            desired_symbols = poll_resp.get("desiredSymbols", [])
            to_unsubscribe = poll_resp.get("unsubscribe", [])
            to_subscribe = poll_resp.get("subscribe", [])
            now_monotonic = time.monotonic()
            revision_changed = desired_revision != owner.last_attempted_revision
            native_keepalive_due = (
                now_monotonic - owner.last_native_probe_monotonic
                >= NATIVE_KEEPALIVE_INTERVAL_SECONDS
            )
            native_probe_due = bool(
                to_unsubscribe
                or to_subscribe
                or revision_changed
                or native_keepalive_due
                or native_probe_revision > owner.last_native_probe_revision
            )

            # 2. Reconcile: unsubscribe first, then subscribe (batched).
            if to_unsubscribe:
                for i in range(0, len(to_unsubscribe), RECONCILE_BATCH):
                    batch = to_unsubscribe[i : i + RECONCILE_BATCH]
                    tq_wrapper.unsubscribe_hq(batch)
                    owner._active_native.difference_update(batch)
                    print(f"[mist-bridge] unsubscribed: {batch}")

            if to_subscribe:
                for i in range(0, len(to_subscribe), RECONCILE_BATCH):
                    batch = to_subscribe[i : i + RECONCILE_BATCH]
                    tq_wrapper.subscribe_hq(batch, quote_callback)
                    owner._active_native.update(batch)
                    print(f"[mist-bridge] subscribed: {batch}")
                # Stall-confirmed re-arm: the datasource is re-issuing the full
                # desired list (PUSHING) but callbacks are not advancing —
                # subscribe_hq on an already-listed symbol may be a no-op
                # (2026-08-14 suspicion). Re-arm = unsubscribe then subscribe
                # to force the SDK to re-attach delivery. Cooldown-gated.
                if REARM_ENABLED:
                    now_mono = time.monotonic()
                    if (
                        last_rearm_cb_count is not None
                        and counters["callback_count"] == last_rearm_cb_count
                        and now_mono - last_rearm_at >= REARM_MIN_INTERVAL_SECONDS
                    ):
                        print(
                            f"[mist-bridge] re-arm: callback stalled after re-subscribe; "
                            f"unsubscribe+subscribe {to_subscribe}"
                        )
                        for i in range(0, len(to_subscribe), RECONCILE_BATCH):
                            batch = to_subscribe[i : i + RECONCILE_BATCH]
                            tq_wrapper.unsubscribe_hq(batch)
                            tq_wrapper.subscribe_hq(batch, quote_callback)
                        last_rearm_at = now_mono
                    last_rearm_cb_count = counters["callback_count"]

            # 3. Verify native subscription set matches desired (fail-closed).
            # Report the FULL normalized native set — gateway checks convergence
            # via active_set == desired_set. If native has extras, gateway correctly
            # stays non-converged (not hidden by intersection).
            if native_probe_due:
                owner.last_attempted_revision = desired_revision
                owner.last_native_probe_monotonic = time.monotonic()
                native_list = tq_wrapper.get_subscribe_hq_stock_list()
                native_set = {_format_code(s) for s in native_list}
                owner._active_native = native_set
                owner.last_native_probe_revision = native_probe_revision
            else:
                native_set = set(owner._active_native)
            rejected = []
            for sym in desired_symbols:
                if sym not in native_set:
                    rejected.append({"symbol": sym, "reason": "not in native subscription set"})
            # Report active = full normalized native set (NOT desired ∩ native).
            active_list = sorted(native_set)
            result_resp = _post_json(
                BRIDGE_ENDPOINT + "/result",
                {
                    **owner.request_identity(),
                    "desiredRevision": desired_revision,
                    "appliedRevision": desired_revision,
                    "nativeProbeRevision": owner.last_native_probe_revision,
                    "active": active_list,
                    "rejected": rejected,
                },
            )
            result_error = result_resp.get("error", {})
            if result_error:
                if _owner_was_replaced(result_error):
                    print("[mist-bridge] replaced by a newer bridge instance; exiting")
                    return
                if _requires_registration(result_error):
                    print("[mist-bridge] result fenced, re-registering...")
                    while not owner.register():
                        time.sleep(_retry_delay_seconds(result_error, 1))
                    continue
                print(f"[mist-bridge] reconcile result error: {result_error}")
                if result_error.get("retryable"):
                    time.sleep(_retry_delay_seconds(result_error, 1))
                continue
            if result_resp.get("converged"):
                owner.applied_revision = desired_revision
            elif result_resp.get("retryable"):
                time.sleep(_retry_delay_seconds(result_resp, result_resp.get("retryAttempt", 1)))

            # Quotes are pushed inline from the callback; the loop only
            # reconciles subscriptions, reconnects TCP and reports counters.
            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("[mist-bridge] shutting down...")
            break
        except Exception as e:
            print(f"[mist-bridge] main loop error: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)


def _tz_offset_suffix() -> str:
    """Return timezone offset like +08:00."""
    offset = time.timezone if time.daylight == 0 else time.altzone
    sign = "+" if offset <= 0 else "-"
    hours = abs(offset) // 3600
    minutes = (abs(offset) % 3600) // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


if __name__ == "__main__":
    print(
        f"[mist-bridge] starting: build={BRIDGE_BUILD_ID} sha={BRIDGE_ARTIFACT_SHA256[:12]} datasource={DATASOURCE_URL}"
    )
    run_bridge()
