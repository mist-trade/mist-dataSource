"""Integration tests for the full-QMT HTTP polling command bridge route surface."""

import asyncio
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

import qmt.main
from src.datasource.qmt.bridge import QmtCommandGateway
from src.datasource.qmt.realtime.subscription import QmtSubscriptionJournal


@pytest.mark.asyncio
async def test_qmt_bridge_owner_poll_and_result_flow(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.app.state.qmt_command_gateway = gateway
    command = gateway.enqueue("health", {})

    owner_response = await qmt_client.post(
        "/qmt/bridge/owner",
        json={
            "ownerId": "bridge-a",
            "startedAt": "2026-07-04T10:00:00+08:00",
            "bridgeBuildId": "test-bridge-v1",
            "bridgeArtifactSha256": "a" * 64,
        },
    )
    identity = owner_response.json()
    poll_response = await qmt_client.post(
        "/qmt/bridge/poll",
        json={
            "ownerId": "bridge-a",
            "leaseToken": identity["leaseToken"],
            "generation": identity["generation"],
            "limit": 1,
        },
    )
    result_response = await qmt_client.post(
        "/qmt/bridge/result",
        json={
            "ownerId": "bridge-a",
            "leaseToken": identity["leaseToken"],
            "generation": identity["generation"],
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
    qmt.main.app.state.qmt_command_gateway = gateway
    gateway.register_owner("bridge-health")

    response = await qmt_client.get("/qmt/bridge/health")

    assert response.status_code == 200
    assert response.json()["ownerId"] == "bridge-health"


@pytest.mark.asyncio
async def test_qmt_bridge_command_route_enqueues_and_exposes_result(qmt_client):
    gateway = QmtCommandGateway()
    qmt.main.app.state.qmt_command_gateway = gateway

    owner_response = await qmt_client.post(
        "/qmt/bridge/owner",
        json={
            "ownerId": "bridge-a",
            "bridgeBuildId": "test-bridge-v1",
            "bridgeArtifactSha256": "b" * 64,
        },
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
    identity = owner_response.json()

    poll_response = await qmt_client.post(
        "/qmt/bridge/poll",
        json={
            "ownerId": "bridge-a",
            "leaseToken": identity["leaseToken"],
            "generation": identity["generation"],
            "limit": 1,
        },
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
            "leaseToken": identity["leaseToken"],
            "generation": identity["generation"],
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
async def test_qmt_bridge_command_route_rejects_retired_realtime_polling_method(
    qmt_client,
):
    gateway = QmtCommandGateway()
    qmt.main.app.state.qmt_command_gateway = gateway

    response = await qmt_client.post(
        "/qmt/bridge/commands",
        json={
            "method": "get_full_tick",
            "params": {"symbols": ["000001.SZ"]},
        },
    )

    assert response.status_code == 422
    assert gateway.health()["pendingCount"] == 0


@pytest.mark.asyncio
async def test_qmt_bridge_command_route_allows_historical_command_outside_trading_session(
    qmt_client,
):
    gateway = QmtCommandGateway()
    qmt.main.app.state.qmt_command_gateway = gateway

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


@pytest.mark.asyncio
async def test_qmt_subscription_poll_result_route_uses_exact_sequence_wire(
    tmp_path: Path,
) -> None:
    gateway = QmtCommandGateway()
    journal = QmtSubscriptionJournal(
        path=tmp_path / "subscription-journal.jsonl",
        rotate_bytes=262_144,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    app = qmt.main.create_qmt_app(
        gateway=gateway,
        subscription_journal=journal,
        unsubscribe_success_values=frozenset({0}),
    )
    controller = app.state.qmt_subscription_controller
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1",
    ) as client:
        owner_response = await client.post(
            "/qmt/bridge/owner",
            json={
                "ownerId": "bridge-subscriptions",
                "bridgeBuildId": "test-bridge-v2",
                "bridgeArtifactSha256": "c" * 64,
            },
        )
        identity = owner_response.json()
        operation = asyncio.create_task(controller.execute("subscribe", symbol="300502.SZ"))
        for _ in range(100):
            if controller.health()["inFlight"]:
                break
            await asyncio.sleep(0)

        poll = await client.post(
            "/qmt/bridge/subscriptions/poll",
            json={
                "ownerId": identity["ownerId"],
                "leaseToken": identity["leaseToken"],
                "generation": identity["generation"],
            },
        )
        assert poll.status_code == 200
        assert poll.json() == {
            "command": {
                "callSequence": 1,
                "method": "subscribe_quote",
                "symbol": "300502.SZ",
            }
        }

        result = await client.post(
            "/qmt/bridge/subscriptions/result",
            json={
                "ownerId": identity["ownerId"],
                "leaseToken": identity["leaseToken"],
                "generation": identity["generation"],
                "callSequence": 1,
                "success": 0,
            },
        )
        assert result.status_code == 200
        assert result.json() == {"accepted": True}
        assert await operation == ("subscribed", {"success": 0})

        empty_poll = await client.post(
            "/qmt/bridge/subscriptions/poll",
            json={
                "ownerId": identity["ownerId"],
                "leaseToken": identity["leaseToken"],
                "generation": identity["generation"],
            },
        )
        assert empty_poll.json() == {"command": None}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "ownerId": "owner",
            "leaseToken": "token",
            "generation": 1,
            "streamEpoch": "forbidden",
        },
        {
            "ownerId": "owner",
            "leaseToken": "token",
            "generation": 1,
            "limit": 1,
        },
    ],
)
async def test_qmt_subscription_poll_rejects_unknown_fields(
    qmt_client: AsyncClient,
    payload: dict[str, object],
) -> None:
    response = await qmt_client.post(
        "/qmt/bridge/subscriptions/poll",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result_fields",
    [
        {},
        {"success": 1, "failure": {"symbol": "300502.SZ", "reason": "failed"}},
        {"success": 1, "streamEpoch": "forbidden"},
        {"failure": None},
    ],
)
async def test_qmt_subscription_result_requires_exact_success_xor_failure(
    qmt_client: AsyncClient,
    result_fields: dict[str, object],
) -> None:
    response = await qmt_client.post(
        "/qmt/bridge/subscriptions/result",
        json={
            "ownerId": "owner",
            "leaseToken": "token",
            "generation": 1,
            "callSequence": 1,
            **result_fields,
        },
    )

    assert response.status_code == 422
