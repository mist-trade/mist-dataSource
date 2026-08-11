"""OTel LoggingHandler content assertions (isolated from init_otel).

These tests exercise LoggingHandler against an in-memory provider directly
(the application path attaches the same handler class to the root logger in
init_otel). Content assertions here keep the exporter in-memory instead of
the real OTLP exporter created by init_otel.
"""

from __future__ import annotations

import logging

from opentelemetry import trace
from opentelemetry.sdk._logs import LoggingHandler

LOGGER_NAME = "test.otel.logs"


def _temporary_logger(provider) -> logging.Logger:
    """Logger with exactly one LoggingHandler attached to the test provider."""
    logger = logging.getLogger(LOGGER_NAME)
    # avoid double-attach across tests
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.INFO)
    handler = LoggingHandler(logger_provider=provider)
    logger.addHandler(handler)
    return logger


def test_logging_handler_forwards_records(log_exporter):
    exporter, provider = log_exporter
    exporter.clear()

    logger = _temporary_logger(provider)
    logger.info("ingest start source=tdx symbol=600519")

    records = exporter.get_finished_logs()
    assert len(records) == 1
    assert records[0].log_record.body == "ingest start source=tdx symbol=600519"
    assert records[0].log_record.severity_text == "INFO"


def test_logrecord_carries_trace_context(log_exporter):
    exporter, provider = log_exporter
    exporter.clear()

    logger = _temporary_logger(provider)
    with trace.get_tracer("test").start_as_current_span("t") as span:
        logger.info("inside span")
        ctx = span.get_span_context()

    records = exporter.get_finished_logs()
    assert len(records) == 1
    assert records[0].log_record.trace_id == ctx.trace_id
    assert records[0].log_record.span_id == ctx.span_id


def test_single_delivery(log_exporter):
    """One log line MUST produce exactly one LogRecord (no duplicate delivery)."""
    exporter, provider = log_exporter
    exporter.clear()

    logger = _temporary_logger(provider)
    logger.warning("ingest reject source=tdx reason=not_ready symbol=600519")

    records = exporter.get_finished_logs()
    assert len(records) == 1


def test_multi_handler_does_not_duplicate(log_exporter):
    """stdout + OTLP handlers on the same logger do not duplicate in OTLP."""
    exporter, provider = log_exporter
    exporter.clear()

    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())  # stdout fallback (no-op in tests)
    logger.addHandler(LoggingHandler(logger_provider=provider))
    logger.info("broadcast source=tdx clients=2")

    records = exporter.get_finished_logs()
    assert len(records) == 1
