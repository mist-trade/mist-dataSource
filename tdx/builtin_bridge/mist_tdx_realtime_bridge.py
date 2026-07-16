#!/usr/bin/env python3
"""mist_tdx_realtime_bridge.py — TDX terminal builtin bridge strategy script.

Runs INSIDE the TDX terminal's tqcenter Python environment (Python 3.7 +
stdlib + tqcenter only). Communicates with the datasource experimental gateway
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
RECONCILE_BATCH = 50
DIRTY_QUEUE_MAX = 200

# Contract tuple (must match gateway ACCEPTED_* constants).
ACQUISITION_PROFILE = "tdx.get_market_snapshot"
SCHEMA_VERSION = 0
DRAFT_REVISION = 1

# Build identity (computed at load time).
BRIDGE_BUILD_ID = "mist-tdx-bridge-v0.1"


def _compute_artifact_sha() -> str:
    """Compute SHA256 of this script file for artifact identity."""
    script_path = os.path.abspath(__file__)
    try:
        with open(script_path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return "unknown"


BRIDGE_ARTIFACT_SHA256 = _compute_artifact_sha()


# --- HTTP helpers (stdlib only) ---------------------------------------


def _post_json(url: str, payload: dict) -> dict:
    """POST JSON to gateway, return parsed response. Raises on network error."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8"))


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

    def next_producer_sequence(self) -> int:
        self._producer_seq += 1
        return self._producer_seq

    def register(self) -> bool:
        """Register with gateway. Returns True on success."""
        resp = _post_json(
            BRIDGE_ENDPOINT + "/owner",
            {
                "ownerId": self.owner_id,
                "bridgeBuildId": BRIDGE_BUILD_ID,
                "bridgeArtifactSha256": BRIDGE_ARTIFACT_SHA256,
                "acquisitionProfile": ACQUISITION_PROFILE,
                "schemaVersion": SCHEMA_VERSION,
                "draftRevision": DRAFT_REVISION,
            },
        )
        if "leaseToken" not in resp:
            print(f"[mist-bridge] registration failed: {resp}")
            return False
        self.lease_token = resp["leaseToken"]
        self.stream_epoch = resp.get("streamEpoch")
        self.applied_revision = -1
        self._active_native = set()
        # Do NOT log lease token (even partial) — per golden contract.
        print(f"[mist-bridge] registered: epoch={self.stream_epoch} build={BRIDGE_BUILD_ID}")
        return True


# --- tqcenter wrapper -------------------------------------------------


class TqCenterWrapper:
    """Wraps tqcenter.tq SDK calls. Uses fake tq for macOS testing."""

    def __init__(self) -> None:
        self._tq = None
        self._is_fake = False

    def initialize(self) -> None:
        # Fail-closed: if MIST_BRIDGE_USE_FAKE_TQ is NOT set, missing tqcenter
        # is a fatal error (production must not silently send fake data).
        use_fake = os.environ.get("MIST_BRIDGE_USE_FAKE_TQ", "") == "1"
        if use_fake:
            print("[mist-bridge] MIST_BRIDGE_USE_FAKE_TQ=1, using fake (test only)")
            self._tq = _FakeTq()
            self._is_fake = True
            return
        try:
            from tqcenter import tq  # type: ignore[import-not-found]

            tq.initialize(__file__)
            self._tq = tq
            self._is_fake = False
            print("[mist-bridge] tqcenter initialized (real SDK)")
        except ImportError:
            raise SystemExit(
                "[mist-bridge] FATAL: tqcenter not available and MIST_BRIDGE_USE_FAKE_TQ!=1."
                " This script must run inside the TDX terminal. Set MIST_BRIDGE_USE_FAKE_TQ=1"
                " only for testing."
            )

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


class _FakeTq:
    """Fake tqcenter for macOS development/testing."""

    def __init__(self) -> None:
        self._subscriptions: set[str] = set()
        self._tick_count = 0

    def initialize(self, file_path: str) -> None:
        pass

    def subscribe_hq(self, codes: list[str], callback) -> None:
        self._subscriptions.update(codes)
        # Simulate immediate callback for each.
        for code in codes:
            self._tick_count += 1
            callback(json.dumps({"Code": code, "ErrorId": "0"}))

    def unsubscribe_hq(self, codes: list[str]) -> None:
        for c in codes:
            self._subscriptions.discard(c)

    def get_market_snapshot(self, code: str) -> dict:
        return {
            "Code": code,
            "ErrorId": "0",
            "Now": "1685.0",
            "Open": "1670.0",
            "Max": "1690.0",
            "Min": "1665.0",
            "LastClose": "1672.5",
            "Volume": "12345600",
            "Amount": "20800000000",
            "AsOf": "2026-07-17T14:30:00.000+08:00",
        }

    def get_subscribe_hq_stock_list(self) -> list[str]:
        return list(self._subscriptions)


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
        print("[mist-bridge] waiting to register...")
        time.sleep(POLL_INTERVAL_SECONDS)

    print("[mist-bridge] starting main loop")
    while True:
        try:
            # 1. Poll desired state.
            poll_resp = _post_json(
                BRIDGE_ENDPOINT + "/poll",
                {
                    "leaseToken": owner.lease_token,
                    "appliedRevision": owner.applied_revision,
                },
            )
            if "error" in poll_resp:
                err = poll_resp["error"]
                if err.get("code") in ("TDX_BRIDGE_NO_OWNER", "TDX_BRIDGE_LEASE_INVALID"):
                    print("[mist-bridge] lease lost, re-registering...")
                    while not owner.register():
                        time.sleep(POLL_INTERVAL_SECONDS)
                    continue
                # Other errors: log and continue.
                print(f"[mist-bridge] poll error: {err}")
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

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
            native_list = tq_wrapper.get_subscribe_hq_stock_list()
            native_set = {_format_code(s) for s in native_list}
            rejected = []
            for sym in desired_symbols:
                # Check if symbol is in native subscription list (SDK actually subscribed).
                if sym not in native_set:
                    rejected.append({"symbol": sym, "reason": "not in native subscription set"})
            # Report active = actual native set ∩ desired (not blindly optimistic).
            active_list = [s for s in desired_symbols if s in native_set]
            owner._active_native = set(active_list)
            result_resp = _post_json(
                BRIDGE_ENDPOINT + "/result",
                {
                    "leaseToken": owner.lease_token,
                    "desiredRevision": desired_revision,
                    "appliedRevision": desired_revision,
                    "active": active_list,
                    "rejected": rejected,
                },
            )
            if result_resp.get("converged"):
                owner.applied_revision = desired_revision

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
                try:
                    snap_resp = _post_json(
                        BRIDGE_ENDPOINT + "/snapshot",
                        {
                            "leaseToken": owner.lease_token,
                            "symbol": code,
                            "producerSequence": owner.next_producer_sequence(),
                            "capturedAt": captured_at,
                            "native": native,
                        },
                    )
                    if not snap_resp.get("accepted"):
                        err = snap_resp.get("error", {})
                        if err.get("code") in ("TDX_BRIDGE_DUPLICATE_PRODUCER_SEQUENCE",):
                            pass  # Expected on retry.
                        else:
                            print(f"[mist-bridge] snapshot rejected for {code}: {err}")
                except urllib.error.URLError as e:
                    print(f"[mist-bridge] snapshot POST error for {code}: {e}")

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
