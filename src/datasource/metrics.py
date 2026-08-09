"""Datasource realtime-chain health metrics (OTel metrics API, low cardinality).

Instrumentation is registered ONCE by ``init_metrics()`` (called after
``init_otel()`` in each entrypoint). Helper functions only reference the
already-registered instruments — calling create_counter/create_gauge twice
with the same name raises DuplicateMetricError.

Rejection reasons are bounded enums (see design D3); symbols, owner IDs,
lease tokens and free-form errors NEVER appear as metric labels.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from opentelemetry import metrics
from opentelemetry.metrics import Observation

_INSTRUMENTS: dict[str, Any] = {}
_SOURCE = "unknown"


def _meter() -> metrics.Meter:
    # Lazy: get_meter consults the global provider at call time (the cached
    # _ProxyMeter also delegates, but lazy is clearer).
    return metrics.get_meter("mist-datasource", "0.1.0")


def init_metrics() -> None:
    """Register all instruments exactly once. Call after ``init_otel()``."""
    if _INSTRUMENTS:
        return
    m = _meter()
    _INSTRUMENTS["accepted"] = m.create_counter(
        "mist_datasource_snapshot_accepted_total",
        description="Accepted bridge snapshots per source",
    )
    _INSTRUMENTS["rejected"] = m.create_counter(
        "mist_datasource_snapshot_rejected_total",
        description="Rejected bridge snapshots per source and reason",
    )
    _INSTRUMENTS["bridge_ready"] = m.create_gauge(
        "mist_datasource_bridge_ready",
        description="Bridge readiness per source (1 ready / 0 not)",
    )
    _INSTRUMENTS["owner_stale"] = m.create_gauge(
        "mist_datasource_owner_stale",
        description="Owner staleness per source (1 stale / 0 fresh)",
    )
    _INSTRUMENTS["control"] = m.create_counter(
        "mist_datasource_control_total",
        description="Subscription control outcomes",
    )
    _INSTRUMENTS["ws_clients"] = m.create_gauge(
        "mist_datasource_ws_clients",
        description="Connected WebSocket clients per source",
    )
    _INSTRUMENTS["startup_ok"] = m.create_gauge(
        "mist_datasource_startup_ok",
        description="Successful startup per source (1 ok; absent after crash)",
    )


def register_snapshot_age_callback(source: str, factory: Callable[[], float | None]) -> None:
    """Register the snapshot-age observable gauge (idempotent).

    Call from the entrypoint once the gateway instance exists:
        register_snapshot_age_callback(
            lambda: gateway.snapshot_age_seconds(),
        )
    The gauge label set is {"source": <source>}; the source is captured by the
    closure when the entrypoint builds the factory.
    """
    if "age" in _INSTRUMENTS:
        return

    def _collect(_options: Any) -> list[Observation]:
        value = factory()
        if value is None:
            return []
        return [Observation(value, {"source": source})]

    _INSTRUMENTS["age"] = _meter().create_observable_gauge(
        "mist_datasource_snapshot_age_seconds",
        description="Seconds since last accepted snapshot per source",
        callbacks=[_collect],
    )


def record_snapshot_accepted(source: str) -> None:
    inst = _INSTRUMENTS.get("accepted")
    if inst is not None:
        inst.add(1, {"source": source})


def record_snapshot_rejected(source: str, reason: str) -> None:
    inst = _INSTRUMENTS.get("rejected")
    if inst is not None:
        inst.add(1, {"source": source, "reason": reason})


def set_bridge_ready(source: str, ok: bool) -> None:
    inst = _INSTRUMENTS.get("bridge_ready")
    if inst is not None:
        inst.set(1 if ok else 0, {"source": source})


def set_owner_stale(source: str, stale: bool) -> None:
    inst = _INSTRUMENTS.get("owner_stale")
    if inst is not None:
        inst.set(1 if stale else 0, {"source": source})


def record_control(source: str, operation: str, result: str, reason: str) -> None:
    inst = _INSTRUMENTS.get("control")
    if inst is not None:
        inst.add(
            1,
            {
                "source": source,
                "operation": operation,
                "result": result,
                "reason": reason,
            },
        )


def set_ws_clients(source: str, count: int) -> None:
    inst = _INSTRUMENTS.get("ws_clients")
    if inst is not None:
        inst.set(count, {"source": source})


def set_startup_ok(source: str, ok: bool) -> None:
    inst = _INSTRUMENTS.get("startup_ok")
    if inst is not None:
        inst.set(1 if ok else 0, {"source": source})
