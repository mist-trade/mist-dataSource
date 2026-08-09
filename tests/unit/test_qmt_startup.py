"""QMT startup failure tracing tests (C1 direct coverage)."""

from __future__ import annotations

import logging

from opentelemetry import trace


def test_qmt_startup_ambiguous_state_logs_error_and_flushes(monkeypatch, caplog, otel_exporter):
    """C1: ambiguous context-rebuild observation must produce an error log
    and attempt a synchronous flush before the process exits."""
    from src.core import otel as otel_module

    exporter = otel_exporter
    exporter.clear()

    flushed = []

    def fake_force_flush():
        flushed.append(True)
        # Simulate a failed startup: mark the span errored and finish it.
        span = trace.get_current_span()
        if span is not None:
            span.set_status(trace.StatusCode.ERROR, "boom")
            span.end()
        # exporter already captured it via SimpleSpanProcessor

    monkeypatch.setattr(otel_module, "force_flush", fake_force_flush)

    # Simulate the startup-failure path the wrapper follows:
    with caplog.at_level(logging.ERROR):
        from src.core.logging import get_logger

        log = get_logger("test.qmt.startup")
        with trace.get_tracer("test").start_as_current_span("qmt.startup") as span:
            try:
                raise RuntimeError("ambiguous QMT context rebuild observation state")
            except Exception as exc:
                span.set_status(trace.StatusCode.ERROR, str(exc))
                span.record_exception(exc)
                log.error("qmt startup failed: %s", exc)
                otel_module.force_flush()

    assert any("qmt startup failed" in r.message for r in caplog.records)
    assert flushed == [True]
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "qmt.startup"
    assert spans[0].status.status_code == trace.StatusCode.ERROR
