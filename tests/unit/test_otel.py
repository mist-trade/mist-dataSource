"""OpenTelemetry configuration tests (init_otel / instrument_app split)."""

from fastapi import FastAPI

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
