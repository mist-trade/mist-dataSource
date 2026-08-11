"""Pytest configuration and fixtures."""

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import InMemoryLogExporter, SimpleLogRecordProcessor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from qmt.main import app as qmt_app


@pytest.fixture(scope="session")
def otel_exporter():
    """Shared OTel provider + InMemorySpanExporter for span-assertion tests.

    OTel 1.44 forbids re-setting the global TracerProvider, so all tracing
    tests share one session-scoped provider. Each test clears the exporter
    before exercising code and asserts on freshly finished spans.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    yield exporter


@pytest.fixture(scope="session")
def log_exporter():
    """In-memory logs provider for LoggingHandler assertion tests.

    Unlike the tracer fixture this is passed explicitly to LoggingHandler
    (no global logger-provider set needed), so it is isolated from the
    application's stdout/OTLP handlers.
    """
    exporter = InMemoryLogExporter()
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    yield exporter, provider


@pytest.fixture
async def qmt_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing QMT API."""
    from src.datasource.qmt.realtime.gateway import QmtCommandGateway

    previous_gateway = qmt_app.state.qmt_command_gateway
    gateway = QmtCommandGateway()
    qmt_app.state.qmt_command_gateway = gateway

    try:
        async with AsyncClient(
            transport=ASGITransport(app=qmt_app), base_url="http://test"
        ) as client:
            yield client
    finally:
        qmt_app.state.qmt_command_gateway = previous_gateway
