import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.testclient import TestClient

from qmt.main import create_qmt_app
from qmt.routes import realtime


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
            "source": "qmt",
            "quality": "latest-state",
        }


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
