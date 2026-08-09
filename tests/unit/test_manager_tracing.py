"""WS broadcast tracing tests: send failures are observable, not silent."""

from __future__ import annotations

from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_realtime_snapshot


class _FakeWS:
    def __init__(self, fail: bool = False) -> None:
        self._fail = fail
        self.sent: list[str] = []

    async def accept(self) -> None:
        pass

    async def send_text(self, payload: str) -> None:
        if self._fail:
            raise RuntimeError("boom")
        self.sent.append(payload)


async def test_broadcast_success_no_failure_events(otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()

    manager = ConnectionManager()
    ws = _FakeWS()
    await manager.connect_unique(ws, "client-1")  # type: ignore[arg-type]

    await manager.broadcast(ws_realtime_snapshot("tdx", {"x": 1}))

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "ws.broadcast"
    assert span.attributes.get("clients") == 1
    assert "send_failed" not in span.attributes
    assert ws.sent  # message delivered


async def test_broadcast_send_failure_logged_and_evicted(caplog, otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()

    manager = ConnectionManager()
    ok_ws = _FakeWS()
    bad_ws = _FakeWS(fail=True)
    await manager.connect_unique(ok_ws, "ok")  # type: ignore[arg-type]
    await manager.connect_unique(bad_ws, "bad")  # type: ignore[arg-type]

    await manager.broadcast(ws_realtime_snapshot("tdx", {"x": 1}))

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.attributes.get("send_failed") == 1
    assert any(e.name == "send_failed" for e in span.events)

    # warn log emitted for the failed client
    assert any("send failed source=tdx client=bad" in r.message for r in caplog.records)

    # bad client evicted, ok client remains
    assert "ok" in manager.connected_clients
    assert "bad" not in manager.connected_clients
    assert ok_ws.sent
