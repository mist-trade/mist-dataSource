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

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request

# --- Configuration ----------------------------------------------------

DATASOURCE_URL = os.environ.get("MIST_DATASOURCE_URL", "http://127.0.0.1:9001")
BRIDGE_ENDPOINT = DATASOURCE_URL.rstrip("/") + "/tdx/bridge"
POLL_INTERVAL_SECONDS = 3.0
NATIVE_KEEPALIVE_INTERVAL_SECONDS = 30.0
HTTP_TIMEOUT_SECONDS = 2.0
RETRY_BASE_SECONDS = 0.25
RETRY_MAX_SECONDS = 5.0
RECONCILE_BATCH = 50
DIRTY_QUEUE_MAX = 200

OBSERVABILITY_INTERVAL_SECONDS = 30.0

# E transport: persistent TCP (default) or legacy HTTP POST.
MIST_TDX_TRANSPORT = os.environ.get("MIST_TDX_TRANSPORT", "tcp")  # tcp|http
# Quote API used inside the callback (official example uses get_full_tick;
# fall back to get_market_snapshot if its fields/behavior differ on the box).
MIST_TDX_QUOTE_API = os.environ.get("MIST_TDX_QUOTE_API", "full_tick")  # full_tick|market_snapshot
MIST_TDX_TCP_HOST = os.environ.get("MIST_TDX_TCP_HOST", "127.0.0.1")
MIST_TDX_TCP_PORT = int(os.environ.get("MIST_TDX_TCP_PORT", "9003"))


# Contract tuple (must match gateway ACCEPTED_* constants).
ACQUISITION_PROFILE = "tdx.get_market_snapshot"
SCHEMA_VERSION = 2

# Build identity (computed at load time).
BRIDGE_BUILD_ID = "mist-tdx-realtime-bridge-v2.1"


def _resolve_script_path():
    """Return the terminal script path when the host exposes file semantics."""
    script_path = globals().get("__file__")
    if not isinstance(script_path, str) or not script_path:
        return None
    return os.path.abspath(script_path)


BRIDGE_SCRIPT_PATH = _resolve_script_path()


def _compute_artifact_sha() -> str:
    """Compute SHA256 when the terminal exposes a file-backed script."""
    if BRIDGE_SCRIPT_PATH is None:
        return "unavailable"
    try:
        with open(BRIDGE_SCRIPT_PATH, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return "unavailable"


BRIDGE_ARTIFACT_SHA256 = _compute_artifact_sha()

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


class DirtySymbolQueue:
    """Bounded, coalescing set of symbols needing snapshot fetch.

    Thread-safe: subscribe_hq callback acquires lock to add; worker loop
    acquires lock to swap+clear. No SDK/HTTP calls under lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._symbols: set[str] = set()

    def mark_dirty(self, code: str) -> None:
        """Called from subscribe_hq callback. Lock-protected, returns immediately."""
        with self._lock:
            if len(self._symbols) < DIRTY_QUEUE_MAX:
                self._symbols.add(code)

    def swap_and_clear(self) -> set[str]:
        """Called from worker loop. Returns current dirty set and clears it."""
        with self._lock:
            result = self._symbols
            self._symbols = set()
            return result


# --- Bridge owner state -----------------------------------------------


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
                        "[mist-bridge] previous owner is still active; "
                        "waiting for bounded takeover"
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

    def get_full_tick(self, code: str) -> dict | None:
        try:
            result = self._tq.get_full_tick(code)
            if isinstance(result, str):
                return json.loads(result)
            return result
        except Exception as e:
            print(f"[mist-bridge] get_full_tick error for {code}: {e}")
            return None

    def get_quote(self, code: str) -> dict | None:
        """Quote source used inside the callback (env-switchable)."""
        if MIST_TDX_QUOTE_API == "full_tick":
            return self.get_full_tick(code)
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


def run_bridge() -> None:
    """Main bridge loop. Registers, reconciles subscriptions, pushes quotes."""
    tq_wrapper = TqCenterWrapper()
    tq_wrapper.initialize()

    owner = BridgeOwner()

    # Callback does the full work inline (official TDX example pattern: the
    # terminal supports SDK calls inside the subscribe_hq callback): pull the
    # authoritative quote via get_full_tick (or get_market_snapshot) and push
    # it over the persistent connection. send() is non-blocking — a broken
    # connection drops the frame with a counter; the main loop reconnects.
    def on_quote_update(data_str: str) -> None:
        try:
            data = json.loads(data_str)
            code = data.get("Code")
            if code:
                code = _format_code(code)
                counters["callback_count"] += 1
                native = tq_wrapper.get_quote(code)
                if native is None:
                    counters["fetch_none"] += 1
                    return
                counters["fetch_count"] += 1
                captured_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
                captured_at += _tz_offset_suffix()
                _push_snapshot(owner, sender, counters, code, captured_at, native)
        except Exception:
            pass  # Never raise in callback.

    # Register with gateway (retry on network error).
    while True:
        try:
            if owner.register():
                break
        except Exception as e:
            print(f"[mist-bridge] registration error: {e}")
        time.sleep(owner.registration_retry_seconds)

    # E: persistent TCP transport (default) — register once, then push frames.
    sender = None
    if MIST_TDX_TRANSPORT == "tcp":
        from socket_sender import SocketSender

        sender = SocketSender(MIST_TDX_TCP_HOST, MIST_TDX_TCP_PORT)
        register_frame = {
            "type": "register",
            "provider": "tdx",
            **owner.request_identity(),
            "bridgeBuildId": BRIDGE_BUILD_ID,
            "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
            "acquisitionProfile": ACQUISITION_PROFILE,
            "schemaVersion": SCHEMA_VERSION,
        }
        if not sender.connect(register_frame):
            print("[mist-bridge] TCP connect failed; reconnecting in main loop")

    counters = {
        "callback_count": 0,
        "fetch_count": 0,
        "fetch_none": 0,
        "send_dropped": 0,
    }
    last_obs_at = time.monotonic()

    print("[mist-bridge] starting main loop")
    while True:
        try:
            # 0. Reconnect a broken TCP connection (never inside a callback).
            if MIST_TDX_TRANSPORT == "tcp":
                sender.reconnect_if_needed(register_frame)
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
                    tq_wrapper.subscribe_hq(batch, on_quote_update)
                    owner._active_native.update(batch)
                    print(f"[mist-bridge] subscribed: {batch}")

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
