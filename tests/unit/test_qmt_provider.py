import asyncio

import pytest

from src.datasource.qmt.bridge import QmtCommandGateway
from src.datasource.qmt.operations.market import QmtBridgeError
from src.datasource.qmt.provider import QmtDatasourceProvider


async def _wait_for_pending(gateway: QmtCommandGateway) -> None:
    for _ in range(100):
        if gateway.health()["pendingCount"] == 1:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("QMT bridge command was not enqueued")


@pytest.mark.asyncio
async def test_qmt_provider_get_bars_uses_native_bridge() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    provider = QmtDatasourceProvider()

    request = asyncio.create_task(
        provider.get_bars(
            stock_list=["000001.SZ"],
            period="1d",
            start_time="20260701",
            end_time="20260702",
            count=1,
            fields=["close", "volume"],
            dividend_type="front_ratio",
            fill_data=False,
            include_raw=True,
            command_gateway=gateway,
        )
    )
    await _wait_for_pending(gateway)
    commands = gateway.poll("bridge-a", limit=1)

    assert len(commands) == 1
    assert commands[0].method == "get_market_data_ex"
    assert commands[0].params == {
        "fields": ["close", "volume"],
        "stock_list": ["000001.SZ"],
        "period": "1d",
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
                "close": {"20260701": 10.5},
                "volume": {"20260701": 123.0},
            }
        },
    )

    result = await request

    assert result == {
        "marketData": {
            "000001.SZ": {
                "close": {"20260701": 10.5},
                "volume": {"20260701": 123.0},
            }
        },
        "source": "native_bridge",
        "rawMeta": {
            "source": "native_bridge",
            "method": "get_market_data_ex",
            "commandId": commands[0].command_id,
        },
    }
    assert gateway.health()["resultCount"] == 0


@pytest.mark.asyncio
async def test_qmt_provider_rejects_missing_bridge_owner_without_reading_dat() -> None:
    provider = QmtDatasourceProvider()

    with pytest.raises(QmtBridgeError) as exc_info:
        await provider.get_bars(
            stock_list=["000001.SZ"],
            period="1d",
            start_time=None,
            end_time=None,
            count=1,
            command_gateway=QmtCommandGateway(),
        )

    assert exc_info.value.code == "QMT_BRIDGE_OWNER_MISSING"


@pytest.mark.asyncio
async def test_qmt_provider_preserves_native_bridge_error() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    provider = QmtDatasourceProvider()
    request = asyncio.create_task(
        provider.get_bars(
            stock_list=["000001.SZ"],
            period="1d",
            start_time=None,
            end_time=None,
            count=1,
            command_gateway=gateway,
        )
    )
    await _wait_for_pending(gateway)
    command = gateway.poll("bridge-a", limit=1)[0]
    gateway.post_result(
        "bridge-a",
        command.command_id,
        ok=False,
        error={
            "code": "QMT_COMMAND_FAILED",
            "message": "native history failed",
            "retryable": True,
            "details": {"method": "get_market_data_ex"},
        },
    )

    with pytest.raises(QmtBridgeError) as exc_info:
        await request

    assert exc_info.value.code == "QMT_COMMAND_FAILED"
    assert exc_info.value.details == {"method": "get_market_data_ex"}


@pytest.mark.asyncio
async def test_qmt_provider_rejects_non_mapping_native_result() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    provider = QmtDatasourceProvider()
    request = asyncio.create_task(
        provider.get_bars(
            stock_list=["000001.SZ"],
            period="1d",
            start_time=None,
            end_time=None,
            count=1,
            command_gateway=gateway,
        )
    )
    await _wait_for_pending(gateway)
    command = gateway.poll("bridge-a", limit=1)[0]
    gateway.post_result("bridge-a", command.command_id, ok=True, result=[])

    with pytest.raises(QmtBridgeError) as exc_info:
        await request

    assert exc_info.value.code == "QMT_BRIDGE_INVALID_MARKET_DATA"


@pytest.mark.asyncio
async def test_qmt_provider_expires_unanswered_native_command() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    provider = QmtDatasourceProvider()

    with pytest.raises(QmtBridgeError) as exc_info:
        await provider.get_bars(
            stock_list=["000001.SZ"],
            period="1d",
            start_time=None,
            end_time=None,
            count=1,
            command_gateway=gateway,
            bridge_timeout_seconds=0.01,
        )

    assert exc_info.value.code == "QMT_COMMAND_TIMEOUT"
    assert gateway.health()["pendingCount"] == 0
    assert gateway.health()["resultCount"] == 0
