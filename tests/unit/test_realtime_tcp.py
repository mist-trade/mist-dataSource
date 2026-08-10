"""Protocol tests for the persistent TCP ingestion endpoint (change E)."""

from __future__ import annotations

import asyncio
import json
import struct
from typing import Any

import pytest

from src.datasource.realtime_tcp import (
    FRAME_MAX_BYTES,
    encode_frame,
    handle_connection,
)


def test_frame_roundtrip() -> None:
    payload = {"type": "register", "provider": "tdx", "leaseToken": "tok"}
    raw = encode_frame(payload)
    assert struct.unpack(">I", raw[:4])[0] == len(raw) - 4
    decoded = json.loads(raw[4:].decode("utf-8"))
    assert decoded == payload


def test_frame_too_large_rejected() -> None:
    with pytest.raises(ValueError):
        encode_frame({"type": "snapshot", "blob": "x" * (FRAME_MAX_BYTES + 1)})


async def _run_connection(
    frames: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Drive handle_connection over an in-memory reader/writer pair."""
    calls: list[dict[str, Any]] = []

    async def fake_ingest(frame: dict[str, Any]) -> None:
        calls.append(frame)

    # Build a reader whose readexactly serves the encoded frames, and a writer
    # that swallows output.
    raw = b"".join(encode_frame(f) for f in frames)

    class FakeReader:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._pos = 0

        async def readexactly(self, n: int) -> bytes:
            chunk = self._data[self._pos : self._pos + n]
            if len(chunk) < n:
                raise asyncio.IncompleteReadError(chunk, n)
            self._pos += n
            return chunk

    class FakeWriter:
        def __init__(self) -> None:
            self.written: list[bytes] = []

        def write(self, data: bytes) -> None:
            self.written.append(data)

        async def drain(self) -> None:
            return

        def close(self) -> None:
            return

        def get_extra_info(self, name: str) -> Any:
            if name == "peername":
                return ("127.0.0.1", 12345)
            return None

    writer = FakeWriter()
    await handle_connection(FakeReader(raw), writer, provider="tdx", ingest=fake_ingest)
    return calls, [w.decode("utf-8", "replace") for w in writer.written]


async def test_connection_requires_register_first() -> None:
    calls, written = await _run_connection(
        [{"type": "snapshot", "symbol": "600519.SH"}]
    )
    assert calls == []
    assert any("register_required" in w for w in written)


async def test_snapshot_frames_invoke_ingest() -> None:
    calls, _ = await _run_connection(
        [
            {"type": "register", "provider": "tdx", "bridgeBuildId": "b1"},
            {
                "type": "snapshot",
                "leaseToken": "tok",
                "streamEpoch": "ep",
                "symbol": "600519.SH",
                "capturedAt": "2026-08-10T10:00:01+08:00",
                "native": {"Now": 1350.5, "Volume": "100", "Amount": "135000"},
            },
            {"type": "observability", "counters": {"callback_count": 3}},
        ],
    )
    assert len(calls) == 1
    assert calls[0]["symbol"] == "600519.SH"
    assert calls[0]["native"]["Now"] == 1350.5


async def test_unknown_frame_type_warned_without_ingest() -> None:
    calls, _ = await _run_connection(
        [
            {"type": "register", "provider": "tdx"},
            {"type": "mystery", "x": 1},
        ],
    )
    assert calls == []


class AsyncNoop:
    async def __call__(self, _frame: dict[str, Any]) -> None:
        return None
