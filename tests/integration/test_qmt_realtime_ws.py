from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.testclient import TestClient

from qmt.main import create_qmt_app
from qmt.routes import realtime
from src.datasource.qmt.realtime.subscription import QmtSubscriptionJournal


def test_qmt_builtin_mounts_formal_realtime_websocket() -> None:
    app = create_qmt_app(realtime_mode="builtin")
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/realtime/qmt/backend-test") as websocket,
    ):
        ready = websocket.receive_json()
        assert ready["type"] == "realtime.ready"
        assert ready["provider"] == "qmt"
        assert ready["data"] == {
            **ready["data"],
            "mode": "builtin",
            "schemaVersion": 2,
            "source": "QMT",
            "quality": "latest-state",
        }
        assert "bridge" not in ready["data"]
        assert "collectorReady" not in ready["data"]
        assert "generation" not in ready["data"]
        assert "ownerId" not in ready["data"]


def test_qmt_ready_waits_for_startup_reconciliation_terminal_phase() -> None:
    app = create_qmt_app(realtime_mode="builtin")
    controller = cast(Any, app.state.qmt_subscription_controller)
    reconcile = AsyncMock()
    controller.reconcile_startup = reconcile

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/realtime/qmt/backend-test") as websocket,
    ):
        assert websocket.receive_json()["type"] == "realtime.ready"

    reconcile.assert_awaited_once_with()


def test_qmt_journal_damage_is_degraded_but_does_not_block_transport_ready(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=262_144,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    assert journal.healthy is False
    app = create_qmt_app(
        realtime_mode="builtin",
        subscription_journal=journal,
    )

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/realtime/qmt/backend-test") as websocket,
    ):
        assert websocket.receive_json()["type"] == "realtime.ready"
        subscriptions = client.get("/health").json()["subscriptions"]

    assert subscriptions["ready"] is False
    assert subscriptions["reconciliationRequired"] is True
    assert subscriptions["startupReconciliation"]["phase"] == "degraded"


def test_qmt_root_health_uses_common_bridge_path() -> None:
    app = create_qmt_app(realtime_mode="builtin")
    with TestClient(app) as client:
        body = client.get("/health").json()

    assert body["bridge"]["ready"] is False
    assert body["bridge"]["ownerGeneration"] == 0
    assert "collectorReady" not in body


def test_qmt_off_does_not_mount_realtime_routes() -> None:
    app = create_qmt_app(realtime_mode="off")
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/ws/realtime/qmt/{client_id}" not in paths
    assert "/qmt/realtime/health" not in paths


def test_qmt_realtime_diagnostics_accept_explicit_docker_host_gateway(monkeypatch) -> None:
    request = Request({"type": "http", "client": ("172.18.0.1", 40123)})
    monkeypatch.setattr(
        realtime,
        "is_trusted_local_bridge_peer",
        lambda host: host == "172.18.0.1",
    )

    realtime._require_loopback(request)


def test_qmt_realtime_diagnostics_reject_untrusted_container_peer(monkeypatch) -> None:
    request = Request({"type": "http", "client": ("172.18.0.2", 40123)})
    monkeypatch.setattr(realtime, "is_trusted_local_bridge_peer", lambda _host: False)

    with pytest.raises(HTTPException) as exc:
        realtime._require_loopback(request)

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "QMT_REALTIME_NOT_LOOPBACK"
