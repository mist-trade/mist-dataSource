from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from qmt.main import create_qmt_app

BEIJING = ZoneInfo("Asia/Shanghai")


def _experimental_app():
    return create_qmt_app(realtime_mode="builtin_experimental")


def test_qmt_realtime_mode_off_mounts_no_experimental_runtime():
    app = create_qmt_app(realtime_mode="off")
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/ws/qmt-experimental/{client_id}" not in paths
    assert "/qmt/realtime/health" not in paths
    assert not hasattr(app.state, "qmt_realtime_collector")
    assert not hasattr(app.state, "qmt_experimental_ws_manager")


def test_qmt_experimental_transport_has_no_product_persistence_dependencies():
    root = Path(__file__).parents[2]
    source = "\n".join(
        (root / relative).read_text(encoding="utf-8")
        for relative in (
            "qmt/main.py",
            "qmt/routes/ws.py",
            "qmt/routes/realtime.py",
            "src/datasource/qmt/realtime.py",
        )
    )

    for forbidden in (
        "KEntity",
        "KRepository",
        "persist",
        "aggregator",
        "scanner",
        "signal",
        "alert",
        "trade_order",
        "/v1/market/snapshots/latest",
        "/ws/quote/",
    ):
        assert forbidden not in source


def test_qmt_realtime_unknown_mode_fails_before_app_is_exposed():
    with pytest.raises(ValueError, match="QMT_REALTIME_MODE"):
        create_qmt_app(realtime_mode="product")


def test_qmt_websocket_ready_ping_and_subscription_contract():
    app = _experimental_app()
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/qmt-experimental/test-qmt") as ws,
    ):
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["provider"] == "qmt"
        assert ready["data"]["payloadType"] == "qmt.experimental.snapshot"
        assert ready["data"]["schemaVersion"] == 0
        assert ready["data"]["draftRevision"] == 1
        assert ready["data"]["acquisitionProfile"] == "qmt.get_full_tick.v0"
        assert ready["data"]["sequence"] == 0
        assert ready["data"]["active"] == []
        assert ready["data"]["streamEpoch"]

        ws.send_json({"type": "ping"})
        assert ws.receive_json()["type"] == "pong"

        ws.send_json(
            {
                "type": "sync_subscriptions",
                "symbols": ["600030.SH", "600030.SH"],
            }
        )
        subscribed = ws.receive_json()
        assert subscribed["type"] == "subscribed"
        assert subscribed["data"] == {
            "accepted": ["600030.SH"],
            "rejected": [],
            "active": ["600030.SH"],
        }


def test_qmt_websocket_rejects_unknown_fields_and_bounds_subscriptions():
    app = _experimental_app()
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/qmt-experimental/qmt-bounds") as ws,
    ):
        ws.receive_json()
        ws.send_json({"type": "ping", "legacy": True})
        assert ws.receive_json()["data"]["code"] == "DATASOURCE_WS_UNKNOWN_FIELDS"

        ws.send_json(
            {
                "type": "sync_subscriptions",
                "symbols": [
                    "000001.SZ",
                    "000002.SZ",
                    "600000.SH",
                    "600001.SH",
                    "600002.SH",
                    "600003.SH",
                    "BAD",
                ],
            }
        )
        response = ws.receive_json()["data"]
        assert len(response["active"]) == 5
        assert [item["code"] for item in response["rejected"]] == [
            "QMT_EXPERIMENTAL_ALLOWLIST_LIMIT",
            "QMT_EXPERIMENTAL_SYMBOL_INVALID",
        ]


def test_qmt_experimental_health_is_detailed_and_loopback_only():
    app = _experimental_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        response = client.get("/qmt/realtime/health")
        assert response.status_code == 200
        assert response.json()["payloadType"] == "qmt.experimental.snapshot"
        assert response.json()["bridge"]["ready"] is False
        unknown = client.get("/qmt/realtime/health?legacy=true")
        assert unknown.status_code == 422
        assert unknown.json()["detail"]["code"] == "QMT_REALTIME_UNKNOWN_FIELDS"

    with TestClient(app, client=("203.0.113.1", 50000)) as remote:
        response = remote.get("/qmt/realtime/health")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "QMT_REALTIME_NOT_LOOPBACK"


def test_qmt_public_health_remains_compatible_without_realtime_details():
    app = _experimental_app()
    with TestClient(app) as client:
        payload = client.get("/health").json()
        assert payload["status"] == "ok"
        assert "realtime" not in payload


def test_qmt_websocket_follower_takes_over_after_leader_disconnects():
    app = _experimental_app()
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/qmt-experimental/qmt-leader") as leader,
        client.websocket_connect("/ws/qmt-experimental/qmt-follower") as follower,
    ):
        assert leader.receive_json()["data"]["leaderClientId"] == "qmt-leader"
        assert follower.receive_json()["data"]["leaderClientId"] == "qmt-leader"

        follower.send_json({"type": "sync_subscriptions", "symbols": ["600030.SH"]})
        assert follower.receive_json()["data"]["code"] == "DATASOURCE_WS_NOT_LEADER"

        app.state.qmt_realtime_collector.disconnect("qmt-leader")
        follower.send_json({"type": "sync_subscriptions", "symbols": ["600030.SH"]})
        accepted = follower.receive_json()
        assert accepted["data"]["active"] == ["600030.SH"]
        assert app.state.qmt_realtime_collector.leader_client_id == "qmt-follower"


def test_qmt_experimental_replay_uses_real_ws_and_command_bridge_wiring():
    app = create_qmt_app(
        realtime_mode="builtin_experimental",
        collector_now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/qmt-experimental/replay") as ws,
    ):
        ready = ws.receive_json()
        epoch = ready["data"]["streamEpoch"]
        ws.send_json({"type": "sync_subscriptions", "symbols": ["600030.SH"]})
        assert ws.receive_json()["data"]["active"] == ["600030.SH"]

        owner = client.post("/qmt/bridge/owner", json={"ownerId": "replay-owner"})
        assert owner.status_code == 200
        assert client.portal is not None
        client.portal.call(app.state.qmt_realtime_collector.collect_once)
        command = client.post(
            "/qmt/bridge/poll", json={"ownerId": "replay-owner", "limit": 1}
        ).json()["commands"][0]
        client.post(
            "/qmt/bridge/result",
            json={
                "ownerId": "replay-owner",
                "commandId": command["commandId"],
                "ok": True,
                "result": {
                    "600030.SH": {
                        "timetag": "20260714100000",
                        "lastPrice": 29.15,
                        "open": 29.0,
                        "high": 29.2,
                        "low": 28.9,
                        "lastClose": 28.95,
                        "volume": 123456,
                        "amount": 359876543.0,
                    }
                },
            },
        )
        client.portal.call(app.state.qmt_realtime_collector.collect_once)

        snapshot = ws.receive_json()
        assert snapshot["type"] == "qmt.experimental.snapshot"
        assert snapshot["data"]["symbol"] == "600030.SH"
        assert snapshot["data"]["sequence"] == 1
        assert snapshot["data"]["streamEpoch"] != epoch
        assert snapshot["data"]["native"]["lastPrice"] == 29.15
