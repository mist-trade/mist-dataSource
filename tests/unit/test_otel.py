"""OpenTelemetry configuration tests."""

from fastapi import FastAPI

import src.core.otel as otel_module


def test_configure_otel_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    otel_module.shutdown_otel()
    assert otel_module._configured is False

    app = FastAPI()
    otel_module.configure_otel(app, "test-service")
    # no-op: does not throw, stays unconfigured
    assert otel_module._configured is False


def test_configure_otel_idempotent(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:5080")
    otel_module.shutdown_otel()

    app = FastAPI()
    otel_module.configure_otel(app, "test-service")
    assert otel_module._configured is True
    # second call must not throw or re-instrument
    otel_module.configure_otel(app, "test-service-again")
    assert otel_module._configured is True

    otel_module.shutdown_otel()
