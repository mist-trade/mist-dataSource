"""Logging configuration for mist-datasource."""

import logging
import sys

from opentelemetry import trace

from src.core.config import settings


class TraceContextFormatter(logging.Formatter):
    """Formatter that injects the active OTel trace/span id into every line.

    When a span is active (e.g. inside a snapshot ingestion trace), the
    trace id lets an operator correlate a log line back to the trace in
    OpenObserve (and vice versa). Without an active span both columns are
    "-".
    """

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx.is_valid:
            # full 32-hex trace id, matching the OTLP LogRecord top-level
            # field (and backend pino) so both channels correlate by trace_id
            record.trace_id = f"{ctx.trace_id:032x}"
            record.span_id = f"{ctx.span_id:016x}"
        else:
            record.trace_id = "-"
            record.span_id = "-"
        return super().format(record)


def setup_logging() -> None:
    """Configure application logging with OTel trace-context injection."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        TraceContextFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - "
            "trace=%(trace_id)s span=%(span_id)s - %(message)s"
        )
    )
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        handlers=[handler],
    )


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance.

    Args:
        name: Logger name, typically __name__ of the module

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
