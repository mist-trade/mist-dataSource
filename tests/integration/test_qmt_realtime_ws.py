from starlette.testclient import TestClient

from qmt.main import create_qmt_app


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
            "payloadType": "mist.realtime.native_snapshot",
            "schemaVersion": 1,
            "source": "qmt",
            "sequenceScope": "symbol",
            "acquisitionProfile": "qmt.get_full_tick",
        }


def test_qmt_off_does_not_mount_realtime_routes() -> None:
    app = create_qmt_app(realtime_mode="off")
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/ws/realtime/qmt/{client_id}" not in paths
    assert "/qmt/realtime/health" not in paths
