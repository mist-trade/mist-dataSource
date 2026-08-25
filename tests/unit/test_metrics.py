"""Datasource metrics registration tests."""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource

import src.datasource.metrics as ds_metrics


def _setup() -> None:
    metrics.set_meter_provider(
        MeterProvider(resource=Resource.create({}))
    )
    ds_metrics._INSTRUMENTS.clear()
    ds_metrics.init_metrics()


def test_init_metrics_registers_all_instruments() -> None:
    _setup()
    # assert the private registry contains the instruments
    registered = set(ds_metrics._INSTRUMENTS.keys())
    assert {
        "accepted",
        "rejected",
        "bridge_ready",
        "owner_stale",
        "control",
        "ws_clients",
        "startup_ok",
        "reconciliation_required",
    } <= registered


def test_init_metrics_idempotent() -> None:
    _setup()
    first = dict(ds_metrics._INSTRUMENTS)
    ds_metrics.init_metrics()
    assert first == ds_metrics._INSTRUMENTS  # no duplicate registration


def test_helpers_do_not_throw_after_registration() -> None:
    _setup()
    ds_metrics.record_snapshot_accepted("tdx")
    ds_metrics.record_snapshot_rejected("tdx", "symbol_not_converged")
    ds_metrics.set_bridge_ready("tdx", True)
    ds_metrics.set_owner_stale("tdx", False)
    ds_metrics.record_control("tdx", "subscribe", "success", "none")
    ds_metrics.set_ws_clients("tdx", 1)
    ds_metrics.set_startup_ok("qmt", True)
    ds_metrics.set_reconciliation_required("qmt", True)
    ds_metrics.set_reconciliation_required("qmt", False)
    # all instrument references exist
    assert "age" not in ds_metrics._INSTRUMENTS  # age registered separately
