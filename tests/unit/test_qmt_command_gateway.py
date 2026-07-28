import pytest

from src.datasource.qmt.realtime.gateway import (
    QmtBridgeOwnershipError,
    QmtCommandGateway,
    QmtCommandRejectedError,
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
        "bridgeBuildId": None,
        "bridgeArtifactSha256": None,
        "bridgeRuntimeFingerprint": None,
        "ready": False,
        "pendingCount": 0,
        "inFlightCount": 0,
        "resultCount": 0,
        "maxOutstandingCommands": 64,
        "maxRetainedResults": 64,
        "resultTtlSeconds": 300.0,
        "maxPollLimit": 16,
        "maxCommandBytes": 65_536,
        "maxResultBytes": 8_388_608,
        "maxRetainedResultBytes": 33_554_432,
        "retainedResultBytes": 0,
        "oldestPendingAgeSeconds": None,
        "oldestResultAgeSeconds": None,
        "commandRejectionTotals": [
            {"reason": "capacity", "value": 0},
            {"reason": "command_invalid", "value": 0},
            {"reason": "command_too_large", "value": 0},
            {"reason": "result_capacity", "value": 0},
            {"reason": "result_invalid", "value": 0},
            {"reason": "result_too_large", "value": 0},
        ],
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


def test_qmt_command_gateway_rejects_retired_generation_result() -> None:
    clock = ManualClock()
    gateway = QmtCommandGateway(clock=clock, owner_stale_after_seconds=5.0)
    first = gateway.register_owner("bridge-a")
    command = gateway.enqueue("get_full_tick", {"symbols": ["300502.SZ"]})
    gateway.poll(
        first.owner_id,
        lease_token=first.lease_token,
        generation=first.generation,
    )

    clock.advance(6.0)
    second = gateway.register_owner("bridge-a")
    assert second.generation == first.generation + 1
    assert second.lease_token != first.lease_token

    with pytest.raises(QmtBridgeOwnershipError):
        gateway.post_result(
            first.owner_id,
            command.command_id,
            lease_token=first.lease_token,
            generation=first.generation,
            ok=True,
            result={"300502.SZ": {}},
        )


def test_qmt_command_gateway_rejects_when_outstanding_capacity_is_full() -> None:
    gateway = QmtCommandGateway(
        max_outstanding_commands=1,
        max_retained_results=1,
        max_retained_result_bytes=1_024,
    )
    gateway.enqueue("health", {})

    with pytest.raises(QmtCommandRejectedError) as caught:
        gateway.enqueue("health", {})

    assert caught.value.code == "QMT_COMMAND_CAPACITY_EXCEEDED"
    assert caught.value.http_status == 429
    assert caught.value.retryable is True
    totals = {
        row["reason"]: row["value"]
        for row in gateway.health()["commandRejectionTotals"]
    }
    assert totals["capacity"] == 1


@pytest.mark.parametrize("limit", [True, 0, 2, 1.5])
def test_qmt_command_gateway_rejects_invalid_poll_limit_without_claiming(
    limit: object,
) -> None:
    gateway = QmtCommandGateway(
        max_poll_limit=1,
        max_retained_result_bytes=65_536,
    )
    owner = gateway.register_owner("bridge-a")
    command = gateway.enqueue("health", {})

    with pytest.raises(ValueError):
        gateway.poll(
            owner.owner_id,
            lease_token=owner.lease_token,
            generation=owner.generation,
            limit=limit,  # type: ignore[arg-type]
        )

    assert gateway.command_state(command.command_id) == "pending"


def test_qmt_command_gateway_rejects_invalid_and_oversized_command_payloads() -> None:
    gateway = QmtCommandGateway(
        max_command_bytes=80,
        max_retained_result_bytes=65_536,
    )

    with pytest.raises(QmtCommandRejectedError) as invalid:
        gateway.enqueue("health", {"value": float("nan")})
    with pytest.raises(QmtCommandRejectedError) as oversized:
        gateway.enqueue("health", {"value": "x" * 200})

    assert invalid.value.code == "QMT_COMMAND_PAYLOAD_INVALID"
    assert invalid.value.retryable is False
    assert oversized.value.code == "QMT_COMMAND_PAYLOAD_TOO_LARGE"
    assert oversized.value.retryable is False
    assert gateway.health()["pendingCount"] == 0


def test_qmt_command_gateway_substitutes_bounded_failure_for_oversized_result() -> None:
    gateway = QmtCommandGateway(
        max_result_bytes=1_024,
        max_retained_result_bytes=65_536,
    )
    owner = gateway.register_owner("bridge-a")
    command = gateway.enqueue("health", {})
    gateway.poll(
        owner.owner_id,
        lease_token=owner.lease_token,
        generation=owner.generation,
    )

    result = gateway.post_result(
        owner.owner_id,
        command.command_id,
        lease_token=owner.lease_token,
        generation=owner.generation,
        ok=True,
        result={"payload": "x" * 2_000},
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error["code"] == "QMT_COMMAND_RESULT_TOO_LARGE"
    assert gateway.health()["retainedResultBytes"] <= 1_024


def test_qmt_command_gateway_prunes_expired_results_and_releases_capacity() -> None:
    clock = ManualClock()
    gateway = QmtCommandGateway(
        clock=clock,
        result_ttl_seconds=5,
        max_outstanding_commands=1,
        max_retained_results=1,
        max_retained_result_bytes=1_024,
    )
    owner = gateway.register_owner("bridge-a")
    command = gateway.enqueue("health", {})
    gateway.poll(owner.owner_id)
    gateway.post_result(owner.owner_id, command.command_id, ok=True, result={})
    assert gateway.command_state(command.command_id) == "completed"

    clock.advance(6)

    assert gateway.command_state(command.command_id) == "unknown"
    assert gateway.health()["retainedResultBytes"] == 0
    assert gateway.enqueue("health", {}).method == "health"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("max_outstanding_commands", 0),
        ("max_retained_results", 0),
        ("result_ttl_seconds", 0),
        ("max_poll_limit", 0),
        ("max_command_bytes", 0),
        ("max_result_bytes", 0),
        ("max_retained_result_bytes", 0),
    ],
)
def test_qmt_command_gateway_rejects_non_positive_limits(
    name: str,
    value: int,
) -> None:
    with pytest.raises(ValueError):
        QmtCommandGateway(**{name: value})
