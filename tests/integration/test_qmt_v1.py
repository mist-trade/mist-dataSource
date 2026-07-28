"""Integration tests for the native QMT datasource surface."""

import asyncio

import pytest

import qmt.main
from src.datasource.qmt.realtime.gateway import QmtCommandGateway


async def _wait_for_pending(gateway: QmtCommandGateway) -> None:
    for _ in range(100):
        if gateway.health()["pendingCount"] == 1:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("QMT bridge command was not enqueued")


@pytest.mark.asyncio
async def test_qmt_v1_bars_query_returns_native_bridge_market_data(qmt_client) -> None:
    gateway = qmt.main.app.state.qmt_command_gateway
    gateway.register_owner("bridge-a")
    request_task = asyncio.create_task(
        qmt_client.post(
            "/v1/bars/query",
            json={
                "fields": ["close", "preClose", "volume", "amount"],
                "stock_list": ["000001.SZ"],
                "period": "1h",
                "start_time": "20260701",
                "end_time": "20260702",
                "count": 1,
                "dividend_type": "front_ratio",
                "fill_data": False,
                "include_raw": False,
            },
        )
    )
    await _wait_for_pending(gateway)
    commands = gateway.poll("bridge-a", limit=1)

    assert len(commands) == 1
    assert commands[0].method == "get_market_data_ex"
    assert commands[0].params == {
        "fields": ["close", "preClose", "volume", "amount"],
        "stock_list": ["000001.SZ"],
        "period": "1h",
        "start_time": "20260701",
        "end_time": "20260702",
        "count": 1,
        "dividend_type": "front_ratio",
        "fill_data": False,
    }
    gateway.post_result(
        "bridge-a",
        commands[0].command_id,
        ok=True,
        result={
            "000001.SZ": {
                "close": {"20260701100000": 10.5},
                "preClose": {"20260701100000": 10.2},
                "volume": {"20260701100000": "1200.12500000"},
                "amount": {"20260701100000": None},
            }
        },
    )

    response = await request_task

    assert response.status_code == 200
    assert response.json()["data"] == {
        "marketData": {
            "000001.SZ": {
                "close": {"20260701100000": 10.5},
                "preClose": {"20260701100000": 10.2},
                "volume": {"20260701100000": "1200.125"},
                "amount": {"20260701100000": None},
            }
        },
        "source": "native_bridge",
    }


@pytest.mark.asyncio
async def test_qmt_v1_bars_query_fails_when_bridge_owner_is_missing(qmt_client) -> None:
    response = await qmt_client.post(
        "/v1/bars/query",
        json={
            "fields": ["close"],
            "stock_list": ["000001.SZ"],
            "period": "1d",
            "count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "QMT_BRIDGE_OWNER_MISSING"
    assert body["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_qmt_v1_bars_query_fails_when_bridge_owner_is_stale(qmt_client) -> None:
    class ManualClock:
        def __init__(self) -> None:
            self.value = 100.0

        def __call__(self) -> float:
            return self.value

    clock = ManualClock()
    gateway = QmtCommandGateway(clock=clock, owner_stale_after_seconds=1.0)
    qmt.main.app.state.qmt_command_gateway = gateway
    gateway.register_owner("bridge-a")
    clock.value += 2.0

    response = await qmt_client.post(
        "/v1/bars/query",
        json={
            "fields": ["close"],
            "stock_list": ["000001.SZ"],
            "period": "1d",
            "count": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "QMT_BRIDGE_OWNER_STALE"
    assert body["error"]["retryable"] is True


@pytest.mark.asyncio
async def test_qmt_v1_bars_query_rejects_tdx_style_fields(qmt_client) -> None:
    response = await qmt_client.post(
        "/v1/bars/query",
        json={
            "symbols": ["000001.SZ"],
            "period": "1d",
            "startTime": "",
            "endTime": "",
            "dividendType": "none",
            "fillData": True,
        },
    )

    assert response.status_code == 422


def test_qmt_http_route_table_keeps_native_v1_health_and_http_bridge() -> None:
    paths = set(qmt.main.app.openapi()["paths"])

    assert "/health" in paths
    assert "/v1/bars/query" in paths
    assert {
        "/qmt/bridge/owner",
        "/qmt/bridge/poll",
        "/qmt/bridge/result",
        "/qmt/bridge/health",
    } <= paths
    assert not any(path.startswith("/api/qmt/") for path in paths)
    assert "/qmt/bridge/ws" not in paths
