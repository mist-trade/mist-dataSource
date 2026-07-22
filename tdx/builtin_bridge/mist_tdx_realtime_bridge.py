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
- producer_sequence for HTTP-retry idempotency.
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
POLL_INTERVAL_SECONDS = 1.0
HTTP_TIMEOUT_SECONDS = 2.0
RETRY_BASE_SECONDS = 0.25
RETRY_MAX_SECONDS = 5.0
RECONCILE_BATCH = 50
DIRTY_QUEUE_MAX = 200

# Contract tuple (must match gateway ACCEPTED_* constants).
ACQUISITION_PROFILE = "tdx.get_market_snapshot"
SCHEMA_VERSION = 1

# Build identity (computed at load time).
BRIDGE_BUILD_ID = "mist-tdx-bridge-v1.1"


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
        self._producer_seq: int = 0
        self._active_native: set[str] = set()
        self.registration_retry_seconds: float = POLL_INTERVAL_SECONDS
        self._last_registration_error_code: str | None = None

    def next_producer_sequence(self) -> int:
        self._producer_seq += 1
        return self._producer_seq

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

    def get_subscribe_hq_stock_list(self) -> list[str]:
        try:
            result = self._tq.get_subscribe_hq_stock_list()
            if isinstance(result, str):
                return json.loads(result)
            return result or []
        except Exception:
            return []


# --- Main bridge loop -------------------------------------------------


def _format_code(raw: str) -> str:
    """Normalize to suffix format (e.g. SH600519 → 600519.SH)."""
    raw = raw.strip().upper()
    if raw.startswith(("SH", "SZ", "BJ")) and len(raw) == 8:
        return raw[2:] + "." + raw[:2]
    return raw


def run_bridge() -> None:
    """Main bridge loop. Registers, reconciles subscriptions, fetches snapshots."""
    tq_wrapper = TqCenterWrapper()
    tq_wrapper.initialize()

    dirty_queue = DirtySymbolQueue()
    owner = BridgeOwner()

    # subscribe_hq callback: mark dirty ONLY.
    def on_quote_update(data_str: str) -> None:
        try:
            data = json.loads(data_str)
            code = data.get("Code")
            if code:
                dirty_queue.mark_dirty(_format_code(code))
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

    print("[mist-bridge] starting main loop")
    while True:
        try:
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
            desired_symbols = poll_resp.get("desiredSymbols", [])
            to_unsubscribe = poll_resp.get("unsubscribe", [])
            to_subscribe = poll_resp.get("subscribe", [])

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
            native_list = tq_wrapper.get_subscribe_hq_stock_list()
            native_set = {_format_code(s) for s in native_list}
            rejected = []
            for sym in desired_symbols:
                if sym not in native_set:
                    rejected.append({"symbol": sym, "reason": "not in native subscription set"})
            # Report active = full normalized native set (NOT desired ∩ native).
            active_list = sorted(native_set)
            owner._active_native = native_set
            result_resp = _post_json(
                BRIDGE_ENDPOINT + "/result",
                {
                    **owner.request_identity(),
                    "desiredRevision": desired_revision,
                    "appliedRevision": desired_revision,
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

            # 4. Fetch dirty symbols and POST snapshots.
            dirty = dirty_queue.swap_and_clear()
            # Only fetch symbols that are in the converged set.
            converged = set(desired_symbols) if result_resp.get("converged") else set()
            to_fetch = dirty & converged
            for code in to_fetch:
                native = tq_wrapper.get_market_snapshot(code)
                if native is None:
                    continue
                captured_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
                captured_at += _tz_offset_suffix()
                # Use a fixed producerSequence for this snapshot; retry with SAME
                # sequence/body so gateway dedup handles network failures.
                producer_seq = owner.next_producer_sequence()
                snapshot_body = {
                    **owner.request_identity(),
                    "symbol": code,
                    "producerSequence": producer_seq,
                    "capturedAt": captured_at,
                    "native": native,
                }
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        snap_resp = _post_json(BRIDGE_ENDPOINT + "/snapshot", snapshot_body)
                        if snap_resp.get("accepted"):
                            break  # Success.
                        err = snap_resp.get("error", {})
                        if err.get("code") == "TDX_BRIDGE_DUPLICATE_PRODUCER_SEQUENCE":
                            break  # Gateway already has it (prior attempt succeeded).
                        if _owner_was_replaced(err):
                            print("[mist-bridge] replaced by a newer bridge instance; exiting")
                            return
                        if _requires_registration(err):
                            print("[mist-bridge] snapshot fenced, re-registering...")
                            while not owner.register():
                                time.sleep(_retry_delay_seconds(err, attempt + 1))
                            break
                        if err.get("retryable") and attempt < max_retries - 1:
                            time.sleep(_retry_delay_seconds(err, attempt + 1))
                            continue
                        print(f"[mist-bridge] snapshot rejected for {code}: {err}")
                        break  # Non-retryable rejection.
                    except urllib.error.URLError as e:
                        if attempt < max_retries - 1:
                            print(
                                f"[mist-bridge] snapshot POST retry {attempt + 1}/{max_retries} for {code}: {e}"
                            )
                            time.sleep(_retry_delay_seconds(None, attempt + 1))
                        else:
                            print(
                                f"[mist-bridge] snapshot POST failed for {code} after {max_retries} retries: {e}"
                            )

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
