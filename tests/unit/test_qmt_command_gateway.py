import pytest

from src.datasource.qmt.command_gateway import (
    QmtBridgeOwnershipError,
    QmtCommandGateway,
    QmtCommandTimeoutError,
)


class ManualClock:
    def __init__(self, value: float = 100.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_qmt_command_gateway_allows_only_one_bridge_owner() -> None:
    gateway = QmtCommandGateway()

    owner = gateway.register_owner("bridge-a")

    assert owner.owner_id == "bridge-a"
    assert gateway.health()["ownerId"] == "bridge-a"
    with pytest.raises(QmtBridgeOwnershipError):
        gateway.register_owner("bridge-b")


def test_qmt_command_gateway_polls_commands_in_fifo_order() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    first = gateway.enqueue("get_market_data_ex", {"stock_list": ["600519.SH"]})
    second = gateway.enqueue("get_full_tick", {"symbols": ["000001.SZ"]})

    commands = gateway.poll("bridge-a", limit=2)

    assert [command.command_id for command in commands] == [
        first.command_id,
        second.command_id,
    ]
    assert [command.method for command in commands] == [
        "get_market_data_ex",
        "get_full_tick",
    ]
    assert gateway.poll("bridge-a", limit=1) == []


def test_qmt_command_gateway_rejects_polling_from_non_owner() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    gateway.enqueue("get_full_tick", {"symbols": ["600519.SH"]})

    with pytest.raises(QmtBridgeOwnershipError):
        gateway.poll("bridge-b", limit=1)


def test_qmt_command_gateway_stores_posted_result() -> None:
    gateway = QmtCommandGateway()
    gateway.register_owner("bridge-a")
    command = gateway.enqueue("get_full_tick", {"symbols": ["600519.SH"]})
    gateway.poll("bridge-a", limit=1)

    gateway.post_result(
        "bridge-a",
        command.command_id,
        ok=True,
        result={"600519.SH": {"last": 1200.0}},
    )

    result = gateway.result_for(command.command_id)
    assert result is not None
    assert result.ok is True
    assert result.result == {"600519.SH": {"last": 1200.0}}


def test_qmt_command_gateway_expires_timed_out_command() -> None:
    clock = ManualClock()
    gateway = QmtCommandGateway(clock=clock)
    gateway.register_owner("bridge-a")
    command = gateway.enqueue(
        "get_full_tick",
        {"symbols": ["600519.SH"]},
        timeout_seconds=5.0,
    )
    gateway.poll("bridge-a", limit=1)

    clock.advance(6.0)
    expired = gateway.expire_timed_out()

    assert expired == [command.command_id]
    result = gateway.result_for(command.command_id)
    assert result is not None
    assert result.ok is False
    assert result.error is not None
    assert result.error["code"] == "QMT_COMMAND_TIMEOUT"
    with pytest.raises(QmtCommandTimeoutError):
        gateway.raise_if_failed(command.command_id)


def test_qmt_command_gateway_expires_command_not_claimed_by_owner() -> None:
    clock = ManualClock()
    gateway = QmtCommandGateway(clock=clock)
    gateway.register_owner("bridge-a")
    command = gateway.enqueue(
        "get_full_tick",
        {"symbols": ["600519.SH"]},
        timeout_seconds=5.0,
    )

    clock.advance(6.0)
    assert gateway.expire_timed_out() == [command.command_id]
    assert gateway.health()["pendingCount"] == 0
    assert gateway.result_for(command.command_id).error["code"] == "QMT_COMMAND_TIMEOUT"


def test_qmt_command_gateway_health_reports_owner_readiness_and_staleness() -> None:
    clock = ManualClock()
    gateway = QmtCommandGateway(clock=clock, owner_stale_after_seconds=5.0)

    assert gateway.health() == {
        "ownerId": None,
        "lastHeartbeatAt": None,
        "ownerAgeSeconds": None,
        "ownerStale": False,
        "ownerGeneration": 0,
        "ready": False,
        "pendingCount": 0,
        "inFlightCount": 0,
        "resultCount": 0,
    }

    gateway.register_owner("bridge-a")
    assert gateway.health()["ready"] is True
    assert gateway.health()["ownerStale"] is False
    assert gateway.health()["ownerAgeSeconds"] == 0

    clock.advance(6.0)
    assert gateway.health()["ready"] is False
    assert gateway.health()["ownerStale"] is True
    assert gateway.health()["ownerAgeSeconds"] == 6.0


def test_qmt_command_gateway_replaces_stale_owner_and_marks_old_commands_failed() -> None:
    clock = ManualClock()
    gateway = QmtCommandGateway(clock=clock, owner_stale_after_seconds=5.0)
    gateway.register_owner("bridge-a")
    command = gateway.enqueue("get_market_data_ex", {"stock_list": ["000001.SZ"]})
    gateway.poll("bridge-a", limit=1)

    clock.advance(6.0)
    owner = gateway.register_owner("bridge-b")

    assert owner.owner_id == "bridge-b"
    assert gateway.health()["ownerId"] == "bridge-b"
    assert gateway.health()["ready"] is True
    assert gateway.health()["inFlightCount"] == 0
    result = gateway.result_for(command.command_id)
    assert result is not None
    assert result.ok is False
    assert result.error is not None
    assert result.error["code"] == "QMT_BRIDGE_OWNER_REPLACED"
