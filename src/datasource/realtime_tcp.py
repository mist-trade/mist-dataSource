"""realtime_tcp.py — persistent TCP ingestion for bridge frames (change E).

Protocol: [uint32 BE length][JSON]. Frame types:

    register       handshake — binds the connection to the bridge owner's
                   lease/epoch (validated against the provider gateway when a
                   validator is injected); snapshot frames get the bound
                   identity injected so provider ingesters can validate
    snapshot       same validation + broadcast pipeline as HTTP /snapshot
    observability  bridge-side counters -> structured log line (OO searchable;
                   the bridge has no OTel SDK)
    error          (reserved) gateway -> bridge rejection / replacement notice

Backpressure: no business queue by design (change design §E.5). The reader
handles each frame inline; a slow downstream shows up as OS-socket backpressure
on the bridge side (write-full drop counters there). Instantaneous jitter is
absorbed by TCP buffers + the asyncio loop.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import struct
from collections.abc import Callable, Coroutine
from typing import Any

FRAME_MAX_BYTES = 64 * 1024  # mirrors bridge-side cap and native safety 64KiB
_log = logging.getLogger(__name__)


def encode_frame(payload: dict[str, Any]) -> bytes:
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(data) > FRAME_MAX_BYTES:
        raise ValueError(f"frame exceeds {FRAME_MAX_BYTES} bytes")
    return struct.pack(">I", len(data)) + data


async def read_frame(reader: asyncio.StreamReader) -> dict[str, Any] | None:
    """Read one length-prefixed JSON frame. None on clean EOF."""
    header = await reader.readexactly(4)
    (length,) = struct.unpack(">I", header)
    if length > FRAME_MAX_BYTES:
        raise ValueError(f"frame length {length} exceeds cap")
    payload = await reader.readexactly(length)
    return json.loads(payload.decode("utf-8"))


async def handle_connection(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    *,
    provider: str,
    ingest: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    validate_owner: Callable[[str, str], Coroutine[Any, Any, bool]]
    | None = None,
) -> None:
    """One bridge connection: register handshake, then snapshot/observability.

    Provider-specific snapshot handling is injected via `ingest` (TDX:
    gateway.post_snapshot + broadcast; QMT: subscription controller which
    publishes internally) — the protocol layer never duplicates validation.
    When `validate_owner` is injected (TDX gateway owner_matches), the register
    frame's lease/epoch must match the active owner before the connection is
    bound; snapshot frames then carry the bound identity injected into them.
    """
    peer = writer.get_extra_info("peername")
    try:
        first = await read_frame(reader)
        if first is None or first.get("type") != "register":
            _log.warning("tcp register missing provider=%s peer=%s", provider, peer)
            await _try_error(writer, "register_required", "first frame must be register")
            return
        lease_token = first.get("leaseToken")
        stream_epoch = first.get("streamEpoch")
        if validate_owner is not None:
            if not isinstance(lease_token, str) or not isinstance(stream_epoch, str):
                _log.warning(
                    "tcp register missing identity provider=%s peer=%s",
                    provider,
                    peer,
                )
                await _try_error(
                    writer, "owner_mismatch", "register must carry leaseToken and streamEpoch"
                )
                return
            owner_ok = await validate_owner(lease_token, stream_epoch)
            if not owner_ok:
                _log.warning(
                    "tcp register rejected provider=%s peer=%s lease=%s",
                    provider,
                    peer,
                    lease_token,
                )
                await _try_error(
                    writer, "owner_mismatch", "register lease/epoch does not match the active owner"
                )
                return
        _log.info(
            "tcp registered provider=%s peer=%s bridgeBuildId=%s",
            provider,
            peer,
            first.get("bridgeBuildId"),
        )
        while True:
            frame = await read_frame(reader)
            if frame is None:
                return
            frame_type = frame.get("type")
            if frame_type == "snapshot":
                # Connection-level identity: the register handshake bound the
                # lease/epoch; inject it so provider ingesters can validate.
                if lease_token is not None:
                    frame.setdefault("leaseToken", lease_token)
                if stream_epoch is not None:
                    frame.setdefault("streamEpoch", stream_epoch)
                try:
                    await ingest(frame)
                except Exception as exc:
                    # Rejections are already counted inside the ingest pipeline.
                    _log.warning(
                        "tcp snapshot reject provider=%s error=%s", provider, exc
                    )
            elif frame_type == "observability":
                _log.info(
                    "bridge observability provider=%s %s",
                    provider,
                    json.dumps(frame.get("counters", {}), sort_keys=True),
                )
            else:
                _log.warning(
                    "tcp unknown frame type=%r provider=%s peer=%s",
                    frame_type,
                    provider,
                    peer,
                )
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        pass  # bridge disconnected — reconnect re-registers
    except Exception as exc:
        _log.warning("tcp connection error provider=%s peer=%s error=%s", provider, peer, exc)
    finally:
        with contextlib.suppress(Exception):
            writer.close()


async def _try_error(writer: asyncio.StreamWriter, code: str, message: str) -> None:
    try:
        writer.write(encode_frame({"type": "error", "code": code, "message": message}))
        await writer.drain()
    except Exception:
        pass


async def serve(
    *,
    host: str,
    port: int,
    provider: str,
    ingest: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    validate_owner: Callable[[str, str], Coroutine[Any, Any, bool]]
    | None = None,
) -> asyncio.AbstractServer:
    """Start the TCP ingestion server (call from the app lifespan)."""
    return await asyncio.start_server(
        lambda reader, writer: handle_connection(
            reader,
            writer,
            provider=provider,
            ingest=ingest,
            validate_owner=validate_owner,
        ),
        host,
        port,
        limit=FRAME_MAX_BYTES + 64,
    )
