"""socket_sender.py — persistent TCP sender for the TDX builtin bridge.

stdlib-only (Python 3.7 + tqcenter): socket + struct + json.

Protocol (mirrors src/datasource/realtime_tcp.py):
    [uint32 BE length][JSON]

Frame types:
    register       first frame after (re)connect — owner lease/epoch identity
    snapshot       one native snapshot (schema-v2 projection, same JSON shape
                   as the HTTP /tdx/bridge/snapshot body)
    observability  bridge-side counters (E-0 throughput observation)

Semantics:
    - latest-state, no business queue: a frame is written out or dropped;
    - write failures / full OS buffer drop the frame with a counter (the
      bridge never blocks the terminal quote thread);
    - reconnect re-sends register, then the caller re-pushes the latest
      snapshot (latest-state: intermediate loss is irrelevant).
"""

from __future__ import annotations

import contextlib
import json
import socket
import struct
import threading
import time

FRAME_MAX_BYTES = 64 * 1024  # gateway native safety cap (64KiB)
RECONNECT_BACKOFF_BASE_SECONDS = 0.5
RECONNECT_BACKOFF_MAX_SECONDS = 5.0
CONNECT_TIMEOUT_SECONDS = 3.0


class SocketSender:
    """One persistent TCP connection to the datasource realtime gateway.

    Thread-safe (callable from the quote worker thread). Never raises —
    failures are counted and surfaced via `snapshot()` counters for the
    observability frame.
    """

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._sock: socket.socket | None = None
        self._register_payload: dict | None = None
        self._backoff = RECONNECT_BACKOFF_BASE_SECONDS
        # Counters (read by the observability frame).
        self.reconnects = 0
        self.send_failures = 0
        self.dropped_frames = 0

    # --- lifecycle ------------------------------------------------------

    def connect(self, register_payload: dict) -> bool:
        """Open the persistent connection and send the register frame."""
        self._register_payload = register_payload
        with self._lock:
            return self._connect_locked()

    def _connect_locked(self) -> bool:
        self._close_locked()
        try:
            sock = socket.create_connection(
                (self._host, self._port), timeout=CONNECT_TIMEOUT_SECONDS
            )
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self._sock = sock
            if self._register_payload is not None:
                self._send_frame_locked(self._register_payload)
            self.reconnects += 1
            self._backoff = RECONNECT_BACKOFF_BASE_SECONDS
            return True
        except Exception:
            self._close_locked()
            return False

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        if self._sock is not None:
            with contextlib.suppress(Exception):
                self._sock.close()
            self._sock = None

    # --- sending --------------------------------------------------------

    def send(self, frame: dict) -> bool:
        """Write one frame. Reconnects once on a broken connection.

        Returns True when the frame was handed to the OS socket buffer.
        False means dropped (counted) — the caller may re-push the latest
        snapshot on the next quote event (latest-state semantics).
        """
        with self._lock:
            if self._sock is None and not self._connect_locked():
                self.dropped_frames += 1
                return False
            try:
                self._send_frame_locked(frame)
                return True
            except Exception:
                self.send_failures += 1
                self._close_locked()
                self.dropped_frames += 1
                return False

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "connected": self._sock is not None,
                "reconnects": self.reconnects,
                "sendFailures": self.send_failures,
                "droppedFrames": self.dropped_frames,
            }

    # --- internals ------------------------------------------------------

    def _send_frame_locked(self, frame: dict) -> None:
        data = json.dumps(frame, separators=(",", ":")).encode("utf-8")
        if len(data) > FRAME_MAX_BYTES:
            raise ValueError(f"frame exceeds {FRAME_MAX_BYTES} bytes")
        header = struct.pack(">I", len(data))
        if self._sock is None:
            raise OSError("not connected")
        self._sock.sendall(header + data)
