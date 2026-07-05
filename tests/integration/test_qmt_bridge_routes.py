"""Integration tests for the full-QMT HTTP polling command bridge route surface."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import qmt.main
from src.datasource.qmt.command_gateway import QmtCommandGateway

BEIJING = ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_qmt_bridge_owner_poll_and_result_flow(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway
    command = gateway.enqueue("health", {})

    owner_response = await qmt_client.post(
        "/qmt/bridge/owner",
        json={"ownerId": "bridge-a", "startedAt": "2026-07-04T10:00:00+08:00"},
    )
    poll_response = await qmt_client.post(
        "/qmt/bridge/poll",
        json={"ownerId": "bridge-a", "limit": 1},
    )
    result_response = await qmt_client.post(
        "/qmt/bridge/result",
        json={
            "ownerId": "bridge-a",
            "commandId": command.command_id,
            "ok": True,
            "result": {"status": "ok"},
        },
    )

    assert owner_response.status_code == 200
    assert owner_response.json()["ownerId"] == "bridge-a"
    assert poll_response.status_code == 200
    assert poll_response.json()["commands"][0]["commandId"] == command.command_id
    assert result_response.status_code == 200
    assert gateway.result_for(command.command_id).result == {"status": "ok"}


@pytest.mark.asyncio
async def test_qmt_bridge_health_reports_gateway_state(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway
    gateway.register_owner("bridge-health")

    response = await qmt_client.get("/qmt/bridge/health")

    assert response.status_code == 200
    assert response.json()["ownerId"] == "bridge-health"


@pytest.mark.asyncio
async def test_qmt_bridge_command_route_enqueues_and_exposes_result(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway

    owner_response = await qmt_client.post(
        "/qmt/bridge/owner",
        json={"ownerId": "bridge-a"},
    )
    enqueue_response = await qmt_client.post(
        "/qmt/bridge/commands",
        json={
            "method": "get_market_data_ex",
            "params": {"stock_list": ["000001.SZ"], "period": "1d", "count": 1},
            "timeoutSeconds": 3,
        },
    )

    assert owner_response.status_code == 200
    assert enqueue_response.status_code == 200
    command_id = enqueue_response.json()["commandId"]

    poll_response = await qmt_client.post(
        "/qmt/bridge/poll",
        json={"ownerId": "bridge-a", "limit": 1},
    )
    assert poll_response.json()["commands"] == [
        {
            "commandId": command_id,
            "method": "get_market_data_ex",
            "params": {"stock_list": ["000001.SZ"], "period": "1d", "count": 1},
            "timeoutSeconds": 3.0,
        }
    ]

    pending_response = await qmt_client.get(f"/qmt/bridge/commands/{command_id}")
    assert pending_response.status_code == 202
    assert pending_response.json()["status"] == "pending"

    await qmt_client.post(
        "/qmt/bridge/result",
        json={
            "ownerId": "bridge-a",
            "commandId": command_id,
            "ok": True,
            "result": {"marketData": {}},
        },
    )
    result_response = await qmt_client.get(f"/qmt/bridge/commands/{command_id}")

    assert result_response.status_code == 200
    assert result_response.json()["ok"] is True
    assert result_response.json()["result"] == {"marketData": {}}


@pytest.mark.asyncio
async def test_qmt_bridge_command_route_rejects_realtime_command_outside_trading_session(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_bridge_now = lambda: datetime(2026, 7, 6, 20, 0, tzinfo=BEIJING)

    response = await qmt_client.post(
        "/qmt/bridge/commands",
        json={
            "method": "get_full_tick",
            "params": {"symbols": ["000001.SZ"]},
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "QMT_REALTIME_OUTSIDE_TRADING_SESSION"
    assert gateway.health()["pendingCount"] == 0


@pytest.mark.asyncio
async def test_qmt_bridge_command_route_allows_historical_command_outside_trading_session(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_bridge_now = lambda: datetime(2026, 7, 6, 20, 0, tzinfo=BEIJING)

    response = await qmt_client.post(
        "/qmt/bridge/commands",
        json={
            "method": "get_market_data_ex",
            "params": {"stock_list": ["000001.SZ"], "period": "1d", "count": 1},
        },
    )

    assert response.status_code == 200
    assert response.json()["method"] == "get_market_data_ex"
    assert gateway.health()["pendingCount"] == 1


@pytest.mark.asyncio
async def test_qmt_bridge_command_route_rejects_unknown_methods(qmt_client):
    response = await qmt_client.post(
        "/qmt/bridge/commands",
        json={"method": "order_stock", "params": {}},
    )

    assert response.status_code == 422


def test_qmt_bridge_route_table_has_no_websocket_endpoint():
    paths = set(qmt.main.app.openapi()["paths"])

    assert "/qmt/bridge/ws" not in paths
