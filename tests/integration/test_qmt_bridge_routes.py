"""Integration tests for the full-QMT command bridge route surface."""

import pytest
from fastapi.testclient import TestClient

import qmt.main
from src.datasource.qmt.command_gateway import QmtCommandGateway


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


def test_qmt_bridge_websocket_accepts_probe_messages():
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway

    with (
        TestClient(qmt.main.app) as client,
        client.websocket_connect("/qmt/bridge/ws?ownerId=bridge-ws") as websocket,
    ):
        ready = websocket.receive_json()
        websocket.send_json({"type": "ping", "id": "probe-1"})
        pong = websocket.receive_json()

    assert ready["type"] == "bridge.ready"
    assert ready["ownerId"] == "bridge-ws"
    assert pong == {"type": "pong", "id": "probe-1", "ownerId": "bridge-ws"}
    assert gateway.health()["ownerId"] == "bridge-ws"


def test_qmt_bridge_websocket_spike_mode_pushes_commands_and_accepts_results():
    gateway = QmtCommandGateway()
    qmt.main.qmt_command_gateway = gateway
    qmt.main.app.state.qmt_command_gateway = gateway

    with (
        TestClient(qmt.main.app) as client,
        client.websocket_connect(
            "/qmt/bridge/ws?ownerId=bridge-ws-spike&mode=spike-command-loop"
        ) as websocket,
    ):
        ready = websocket.receive_json()
        health_command = websocket.receive_json()
        websocket.send_json(
            {
                "type": "bridge.result",
                "id": health_command["id"],
                "ok": True,
                "result": {"ownerId": "bridge-ws-spike"},
            }
        )
        market_command = websocket.receive_json()
        websocket.send_json(
            {
                "type": "bridge.result",
                "id": market_command["id"],
                "ok": True,
                "result": {"000001.SZ": {"close": [10.0]}},
            }
        )
        done = websocket.receive_json()

    assert ready == {"type": "bridge.ready", "ownerId": "bridge-ws-spike"}
    assert health_command["type"] == "bridge.command"
    assert health_command["method"] == "health"
    assert market_command["type"] == "bridge.command"
    assert market_command["method"] == "get_market_data_ex"
    assert market_command["params"]["symbols"] == ["000001.SZ"]
    assert done["type"] == "bridge.done"
    assert done["commandCount"] == 2
