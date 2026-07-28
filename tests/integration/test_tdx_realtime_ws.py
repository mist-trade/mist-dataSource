from fastapi import FastAPI
from starlette.testclient import TestClient

from src.datasource.tdx.realtime.gateway import TdxRealtimeGateway
from src.ws.manager import ConnectionManager
from tdx.routes.realtime import router


def test_backend_syncs_complete_desired_set_over_realtime_websocket() -> None:
    app = FastAPI()
    app.include_router(router)
    gateway = TdxRealtimeGateway()
    async def execute(operation, *, symbol=None, symbols=None):
        assert operation == "sync_subscriptions"
        assert symbol is None
        assert symbols == ["600030.SH"]
        await gateway.sync_desired(symbols)
        return "subscriptions_synced", {"success": None}

    gateway.execute_control = execute
    app.state.tdx_realtime_gateway = gateway
    app.state.tdx_realtime_ws_manager = ConnectionManager()

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/realtime/tdx/backend-test") as websocket,
    ):
        ready = websocket.receive_json()
        assert ready["type"] == "realtime.ready"
        assert ready["provider"] == "tdx"
        assert ready["data"]["source"] == "TDX"
        assert ready["data"]["bridge"] == {
            "ready": False,
            "ownerId": None,
            "ownerGeneration": 0,
            "bridgeBuildId": None,
        }
        assert "tdxRealtimeBridgeReady" not in ready["data"]
        websocket.send_json(
            {"type": "sync_subscriptions", "symbols": ["600030.SH"]}
        )
        synced = websocket.receive_json()
        assert synced["type"] == "subscriptions_synced"
        assert synced["provider"] == "tdx"
        assert synced["data"] == {"success": None}

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
