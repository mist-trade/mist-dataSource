from fastapi import FastAPI
from starlette.testclient import TestClient

from src.datasource.tdx.realtime_gateway import TdxRealtimeGateway
from src.ws.manager import ConnectionManager
from tdx.routes.realtime_ws import router


def test_backend_syncs_complete_desired_set_over_realtime_websocket() -> None:
    app = FastAPI()
    app.include_router(router)
    gateway = TdxRealtimeGateway()
    app.state.tdx_realtime_gateway = gateway
    app.state.tdx_realtime_ws_manager = ConnectionManager()

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/realtime/tdx/backend-test") as websocket,
    ):
        assert websocket.receive_json()["type"] == "realtime.ready"
        websocket.send_json(
            {"type": "sync_subscriptions", "symbols": ["600030.SH"]}
        )
        synced = websocket.receive_json()
        assert synced["type"] == "subscribed"
        assert synced["provider"] == "tdx"
        assert synced["data"] == {
            "accepted": ["600030.SH"],
            "rejected": [],
            "active": ["600030.SH"],
        }

        health = client.portal.call(gateway.health)
        assert health["desiredSymbols"] == 1
        assert health["desiredRevision"] == 1


def test_realtime_websocket_rejects_invalid_subscription_shape() -> None:
    app = FastAPI()
    app.include_router(router)
    app.state.tdx_realtime_gateway = TdxRealtimeGateway()
    app.state.tdx_realtime_ws_manager = ConnectionManager()

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/realtime/tdx/backend-test") as websocket,
    ):
        websocket.receive_json()
        websocket.send_json({"type": "sync_subscriptions", "symbols": "600030.SH"})
        error = websocket.receive_json()
        assert error["type"] == "error"
        assert error["data"]["code"] == "TDX_SUBSCRIPTIONS_INVALID"
