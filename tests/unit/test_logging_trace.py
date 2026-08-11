"""Logging trace-context injection tests."""

from __future__ import annotations

import logging

from opentelemetry import trace

from src.core.logging import TraceContextFormatter


def test_formatter_without_active_span_uses_dash() -> None:
    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "msg", (), None)
    formatter = TraceContextFormatter(
        "%(levelname)s trace=%(trace_id)s span=%(span_id)s %(message)s"
    )
    out = formatter.format(record)
    assert "trace=- span=-" in out


def test_formatter_with_active_span_injects_trace_id(otel_exporter) -> None:
    otel_exporter.clear()

    record = logging.LogRecord("t", logging.INFO, "f.py", 1, "msg", (), None)
    formatter = TraceContextFormatter(
        "%(levelname)s trace=%(trace_id)s span=%(span_id)s %(message)s"
    )
    with trace.get_tracer("test").start_as_current_span("s") as span:
        out = formatter.format(record)
        ctx = span.get_span_context()
        # full 32-hex trace id (matches OTLP LogRecord top-level / backend pino)
        assert f"trace={ctx.trace_id:032x}" in out
        assert f"span={ctx.span_id:016x}" in out
