"""OpenTelemetry initialization for mist-datasource.

zenml-style standalone module: provider setup lives here, the
``FastAPIInstrumentor.instrument_app(app)`` call stays in each entrypoint
(``tdx/main.py`` / ``qmt/main.py``) because it needs the app instance and
must run before the first request.

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


def configure_otel(app: FastAPI, service_name: str) -> None:
    """Configure OTel for an app. Call after ``app = create_*_app()`` and
    before the first request. No-op when the OTLP endpoint is not configured.
    """
    global _configured
    if _configured:
        return
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    resource = Resource.create({"service.name": service_name})

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    FastAPIInstrumentor.instrument_app(app)
    _configured = True


def shutdown_otel() -> None:
    """Reset the configured flag (used by lifespan shutdown)."""
    global _configured
    _configured = False
