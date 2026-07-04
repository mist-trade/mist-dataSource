"""Integration tests for the full-QMT command bridge route surface."""

import pytest

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
