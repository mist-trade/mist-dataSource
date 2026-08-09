"""OpenTelemetry initialization for mist-datasource.

zenml-style standalone module: provider setup lives here, the
``FastAPIInstrumentor.instrument_app(app)`` call stays in each entrypoint
(``tdx/main.py`` / ``qmt/main.py``) because it needs the app instance and
must run before the first request.

Split into two phases (2026-08-09, instrument-datasource-bridge-ingest):
- ``init_otel``: called at module top after ``setup_logging()``, BEFORE app
  creation — so startup failures (e.g. QMT ambiguous context-rebuild state)
  can still emit an errored span before the process exits.
- ``instrument_app``: called after ``app = create_*_app()``.

Design:
- no-op guard: silently skips when ``OTEL_EXPORTER_OTLP_ENDPOINT`` is unset
  (local dev / tests run with zero OTel overhead)
- idempotent: module-level ``_configured`` flag
- single-worker uvicorn, so no multi-process coordination needed
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_configured = False
_tracer_provider: TracerProvider | None = None


def init_otel(service_name: str) -> None:
    """Initialize providers (traces + metrics) without instrumenting the app.

    Call at module top after ``setup_logging()`` and BEFORE app creation, so
    startup failures can still emit an errored span. No-op when the OTLP
    endpoint is not configured. Idempotent.
    """
    global _configured, _tracer_provider
    if _configured:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _tracer_provider = provider

    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    _configured = True


def instrument_app(app: FastAPI) -> None:
    """Instrument a created app (FastAPIInstrumentor). Must run after app
    creation and before the first request. Idempotent via the instrumentor's
    own flag.
    """
    FastAPIInstrumentor.instrument_app(app)


def force_flush() -> None:
    """Synchronously export pending spans. Call on the startup-failure path
    BEFORE re-raising, so the errored span reaches the backend before the
    process exits (BatchSpanProcessor alone would lose it on crash).
    """
    if _tracer_provider is not None:
        _tracer_provider.force_flush()


def shutdown_otel() -> None:
    """Reset the configured flag (used by lifespan shutdown)."""
    global _configured
    _configured = False
