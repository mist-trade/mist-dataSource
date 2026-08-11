"""OpenTelemetry configuration tests (init_otel / instrument_app split)."""

import logging

from fastapi import FastAPI
from opentelemetry.sdk._logs import LoggingHandler

import src.core.otel as otel_module


def test_init_otel_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    otel_module.shutdown_otel()
    assert otel_module._configured is False

    otel_module.init_otel("test-service")
    # no-op: does not throw, stays unconfigured
    assert otel_module._configured is False
    # force_flush on unconfigured provider must not throw
    otel_module.force_flush()


def test_init_otel_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()

    otel_module.init_otel("test-service")
    assert otel_module._configured is True
    # second call must not throw or re-create providers
    otel_module.init_otel("test-service-again")
    assert otel_module._configured is True

    otel_module.shutdown_otel()


def test_force_flush_does_not_throw(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()
    otel_module.init_otel("test-service")
    # must not raise even if the backend is unreachable
    otel_module.force_flush()
    otel_module.shutdown_otel()


def test_instrument_app_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()
    otel_module.init_otel("test-service")

    app = FastAPI()
    otel_module.instrument_app(app)
    # second call is safe (instrumentor's own idempotency flag)
    otel_module.instrument_app(app)

    otel_module.shutdown_otel()


def _logging_handler_count() -> int:
    return sum(1 for h in logging.getLogger().handlers if isinstance(h, LoggingHandler))


def test_init_otel_logs_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    otel_module.shutdown_otel()
    otel_module.init_otel("test-service")
    # no-op: no LoggingHandler attached, logs stay stdout-only
    assert otel_module._configured is False
    assert _logging_handler_count() == 0
    otel_module.force_flush()


def test_init_otel_logs_attaches_handler(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()
    otel_module.init_otel("test-service")
    assert otel_module._configured is True
    assert _logging_handler_count() == 1
    otel_module.shutdown_otel()


def test_init_otel_logs_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()
    otel_module.init_otel("test-service")
    otel_module.init_otel("test-service-again")
    # second init must not attach a second LoggingHandler
    assert _logging_handler_count() == 1
    otel_module.shutdown_otel()


def test_force_flush_flushes_logs(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()
    otel_module.init_otel("test-service")
    # must not raise even if the backend is unreachable (logs branch included)
    otel_module.force_flush()
    otel_module.shutdown_otel()
