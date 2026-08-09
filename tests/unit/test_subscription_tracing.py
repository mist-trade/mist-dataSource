"""QMT subscription accept_snapshot tracing tests (InMemorySpanExporter)."""

from __future__ import annotations

from pathlib import Path

from opentelemetry import trace

from tests.unit.test_qmt_subscription_control import _controller


async def test_accept_snapshot_partial_reject_emits_events(tmp_path: Path, otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()
    controller, published = _controller(tmp_path)
    controller.registry.singles = {"600519.SH": 123}

    result = await controller.accept_snapshot(
        "owner", "token", 1, 123, "2026-07-26T10:00:00+08:00",
        {
            "600519.SH": {"lastPrice": 100.5},
            "BAD_SYMBOL": {"lastPrice": 1.0},  # fails QMT_SYMBOL_PATTERN
        },
    )
    assert result["accepted"] == ["600519.SH"]
    assert result["rejected"][0]["reason"] == "QMT_SNAPSHOT_SYMBOL_INVALID"

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "qmt.snapshot.ingest"
    assert span.status.status_code == trace.StatusCode.OK  # partial accept
    events = {e.name for e in span.events}
    assert "symbol_rejected" in events
    assert "frame_built" in events
    assert published  # accepted symbol was published


async def test_accept_snapshot_all_rejected_marks_error(tmp_path: Path, otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()
    controller, published = _controller(tmp_path)
    controller.registry.singles = {"600519.SH": 123}

    result = await controller.accept_snapshot(
        "owner", "token", 1, 123, "2026-07-26T10:00:00+08:00",
        {"BAD_SYMBOL": {"lastPrice": 1.0}},
    )
    assert result["accepted"] == []

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code == trace.StatusCode.ERROR
    assert not published  # nothing accepted -> not published
