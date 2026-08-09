"""TDX gateway snapshot ingestion tracing tests.

Uses the OTel SDK InMemorySpanExporter to assert real span structure
(name, status, events) without a network backend.
"""

from __future__ import annotations

from contextlib import suppress

from opentelemetry import trace

from src.datasource.tdx.realtime.gateway import (
    GatewayError,
    TdxRealtimeGateway,
)
from tests.unit.test_tdx_subscription_control import _register


async def _converge_symbol(
    gateway: TdxRealtimeGateway, symbol: str = "600519.SH"
) -> tuple[str, str]:
    """Register owner, sync desired, poll, and report convergence so the
    symbol enters _observed_native_symbols (active must equal desired)."""
    await gateway.sync_desired([symbol])
    owner = gateway.owner
    assert owner is not None
    poll = await gateway.poll(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
    )
    await gateway.post_result(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
        desired_revision=poll["desiredRevision"],
        applied_revision=poll["desiredRevision"],
        active=[symbol],
        rejected=[],
        native_probe_revision=poll["nativeProbeRevision"],
    )
    return owner.lease_token, owner.stream_epoch


def _valid_native() -> dict:
    return {
        "LastClose": "100.00",
        "Volume": "10000",
        "Amount": "1000000.00",
        "High": "101.00",
        "Low": "99.00",
        "Open": "100.00",
        "Last": "100.50",
        "ErrorId": "0",
    }


async def test_post_snapshot_accepted_emits_ok_span(otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    lease, epoch = await _converge_symbol(gateway)

    result = await gateway.post_snapshot(
        lease_token=lease,
        stream_epoch=epoch,
        symbol="600519.SH",
        captured_at="2026-08-09T09:30:00+08:00",
        native=_valid_native(),
    )
    assert result["accepted"] is True

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "tdx.snapshot.ingest"
    assert span.status.status_code == trace.StatusCode.OK
    events = {e.name for e in span.events}
    assert "frame_built" in events
    assert "rejected" not in events
    assert span.attributes.get("symbol") == "600519.SH"


async def test_post_snapshot_rejected_symbol_not_converged(otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    owner = gateway.owner
    assert owner is not None

    with suppress(GatewayError):
        await gateway.post_snapshot(
            lease_token=owner.lease_token,
            stream_epoch=owner.stream_epoch,
            symbol="600519.SH",  # not yet converged
            captured_at="2026-08-09T09:30:00+08:00",
            native=_valid_native(),
        )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == "tdx.snapshot.ingest"
    assert span.status.status_code == trace.StatusCode.ERROR
    rejected = [e for e in span.events if e.name == "rejected"]
    assert len(rejected) == 1
    assert rejected[0].attributes.get("reason") == "TDX_BRIDGE_SYMBOL_NOT_CONVERGED"


async def test_post_snapshot_invalid_native_marks_error(otel_exporter) -> None:
    exporter = otel_exporter
    exporter.clear()
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    lease, epoch = await _converge_symbol(gateway)

    bad_native = dict(_valid_native())
    bad_native.pop("Last")  # missing required price

    with suppress(Exception):
        await gateway.post_snapshot(
            lease_token=lease,
            stream_epoch=epoch,
            symbol="600519.SH",
            captured_at="2026-08-09T09:30:00+08:00",
            native=bad_native,
        )

    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code == trace.StatusCode.ERROR
    rejected = [e for e in span.events if e.name == "rejected"]
    assert len(rejected) == 1
    assert rejected[0].attributes.get("reason") == "native_invalid"
