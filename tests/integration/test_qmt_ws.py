from fastapi.testclient import TestClient

from qmt.main import app


def test_qmt_websocket_ready_ping_and_subscription_contract():
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/quote/test-qmt") as ws,
    ):
            ready = ws.receive_json()
            assert ready["type"] == "ready"
            assert ready["provider"] == "qmt"
            assert ready["data"]["active"] == []

            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            assert pong["type"] == "pong"
            assert pong["provider"] == "qmt"

            ws.send_json(
                {
                    "type": "sync_subscriptions",
                    "symbols": ["600030.SH", "600030.SH"],
                }
            )
            subscribed = ws.receive_json()
            assert subscribed["type"] == "subscribed"
            assert subscribed["provider"] == "qmt"
            assert subscribed["data"] == {
                "accepted": ["600030.SH"],
                "rejected": [],
                "active": ["600030.SH"],
            }


def test_qmt_health_exposes_realtime_state():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        realtime = response.json()["realtime"]
        assert realtime["connectionCount"] == 0
        assert realtime["activeSubscriptions"] == []
        assert realtime["inFlight"] is False


def test_qmt_websocket_follower_takes_over_after_leader_disconnects():
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/quote/qmt-leader") as leader,
        client.websocket_connect("/ws/quote/qmt-follower") as follower,
    ):
        assert leader.receive_json()["data"]["leaderClientId"] == "qmt-leader"
        assert follower.receive_json()["data"]["leaderClientId"] == "qmt-leader"

        follower.send_json({"type": "sync_subscriptions", "symbols": ["600030.SH"]})
        rejected = follower.receive_json()
        assert rejected["type"] == "error"
        assert rejected["data"]["code"] == "DATASOURCE_WS_NOT_LEADER"

        app.state.qmt_realtime_collector.disconnect("qmt-leader")
        follower.send_json({"type": "sync_subscriptions", "symbols": ["600030.SH"]})
        accepted = follower.receive_json()
        assert accepted["type"] == "subscribed"
        assert accepted["data"]["active"] == ["600030.SH"]
        assert app.state.qmt_realtime_collector.leader_client_id == "qmt-follower"
