from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src.datasource.qmt.command_gateway import QmtCommandGateway
from src.datasource.qmt.realtime import QmtRealtimeCollector

BEIJING = ZoneInfo("Asia/Shanghai")


@pytest.mark.asyncio
async def test_collector_enqueues_one_batched_command_and_skips_overlap():
    gateway = QmtCommandGateway()
    gateway.register_owner("owner")
    published = []
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=published.append,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH", "000001.SZ", "600030.SH"])

    await collector.collect_once()
    first_health = collector.health()
    assert first_health["inFlight"] is True
    assert gateway.health()["pendingCount"] == 1

    await collector.collect_once()
    assert gateway.health()["pendingCount"] == 1
    assert collector.health()["skippedOverlapCount"] == 1

    command = gateway.poll("owner")[0]
    assert command.method == "get_full_tick"
    assert command.params == {"symbols": ["000001.SZ", "600030.SH"]}


@pytest.mark.asyncio
async def test_collector_publishes_valid_subscribed_native_results():
    gateway = QmtCommandGateway()
    gateway.register_owner("owner")
    published = []
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=published.append,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])

    await collector.collect_once()
    command = gateway.poll("owner")[0]
    native_snapshot = {
        "timetag": "20260714100000",
        "lastPrice": 29.15,
        "open": 29.0,
        "high": 29.2,
        "low": 28.9,
        "lastClose": 28.95,
        "volume": 123456,
        "amount": 359876543.0,
    }
    gateway.post_result(
        "owner",
        command.command_id,
        ok=True,
        result={"600030.SH": native_snapshot},
    )

    assert await collector.collect_once() == 1
    assert published == [
        {
            "payloadType": "qmt.experimental.snapshot",
            "schemaVersion": 0,
            "draftRevision": 1,
            "acquisitionProfile": "qmt.get_full_tick.v0",
            "streamEpoch": collector.stream_epoch,
            "sequence": 1,
            "symbol": "600030.SH",
            "capturedAt": "2026-07-14T10:00:00+08:00",
            "native": native_snapshot,
        }
    ]
    assert collector.health()["lastErrorCode"] is None
    assert collector.health()["lastQuoteAt"] is not None
    assert gateway.health()["resultCount"] == 0
    assert collector.health()["inFlight"] is True
    next_command = gateway.poll("owner")[0]
    assert next_command.command_id != command.command_id
    assert next_command.method == "get_full_tick"
    assert next_command.params == {"symbols": ["600030.SH"]}


@pytest.mark.asyncio
async def test_collector_sequence_is_monotonic_and_owner_replacement_rotates_epoch():
    monotonic = [0.0]
    gateway = QmtCommandGateway(clock=lambda: monotonic[0], owner_stale_after_seconds=1.0)
    gateway.register_owner("owner-a")
    published = []
    epochs = []
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=published.append,
        epoch_publisher=epochs.append,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])

    await collector.collect_once()
    first_epoch = collector.stream_epoch
    assert epochs[-1]["ownerGeneration"] == 1
    command = gateway.poll("owner-a")[0]
    gateway.post_result(
        "owner-a",
        command.command_id,
        ok=True,
        result={"600030.SH": _native_snapshot()},
    )
    await collector.collect_once()
    assert published[-1]["sequence"] == 1
    assert published[-1]["streamEpoch"] == first_epoch

    monotonic[0] = 2.0
    gateway.register_owner("owner-b")
    await collector.collect_once()
    assert collector.stream_epoch != first_epoch
    assert collector.sequence == 0
    assert epochs[-1]["ownerGeneration"] == 2
    assert epochs[-1]["ownerId"] == "owner-b"


def _native_snapshot() -> dict[str, object]:
    return {
        "timetag": "20260714100000",
        "lastPrice": 29.15,
        "open": 29.0,
        "high": 29.2,
        "low": 28.9,
        "lastClose": 28.95,
        "volume": 123456,
        "amount": 359876543.0,
    }


@pytest.mark.asyncio
async def test_collector_uses_command_symbols_when_subscriptions_change_in_flight():
    gateway = QmtCommandGateway()
    gateway.register_owner("owner")
    published = []
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=published.append,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])
    await collector.collect_once()
    command = gateway.poll("owner")[0]

    collector.subscribe(["000001.SZ"])
    gateway.post_result(
        "owner",
        command.command_id,
        ok=True,
        result={
            "600030.SH": {
                "timetag": "20260714100000",
                "lastPrice": 29.15,
                "open": 29.0,
                "high": 29.2,
                "low": 28.9,
                "lastClose": 28.95,
                "volume": 123456,
                "amount": 359876543.0,
            }
        },
    )

    assert await collector.collect_once() == 1
    assert collector.health()["lastErrorCode"] is None
    assert gateway.poll("owner")[0].params == {"symbols": ["000001.SZ", "600030.SH"]}


@pytest.mark.asyncio
async def test_collector_consumes_in_flight_result_after_all_symbols_are_removed():
    gateway = QmtCommandGateway()
    gateway.register_owner("owner")
    published = []
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=published.append,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])
    await collector.collect_once()
    command = gateway.poll("owner")[0]
    collector.sync_subscriptions([])
    gateway.post_result("owner", command.command_id, ok=True, result={"600030.SH": {}})

    assert await collector.collect_once() == 0
    assert collector.health()["inFlight"] is False
    assert collector.health()["state"] == "idle"
    assert gateway.health()["resultCount"] == 0
    assert published == []


@pytest.mark.asyncio
async def test_collector_stays_idle_outside_session():
    gateway = QmtCommandGateway()
    gateway.register_owner("owner")
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=lambda _quote: None,
        now=lambda: datetime(2026, 7, 14, 20, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])

    assert await collector.collect_once() == 0
    assert gateway.health()["pendingCount"] == 0
    assert collector.health()["state"] == "outside_session"


@pytest.mark.asyncio
async def test_collector_rejects_invalid_native_payload_and_records_error():
    gateway = QmtCommandGateway()
    gateway.register_owner("owner")
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=lambda _quote: None,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])
    await collector.collect_once()
    command = gateway.poll("owner")[0]
    gateway.post_result(
        "owner",
        command.command_id,
        ok=True,
        result={"600030.SH": {"timetag": "20260714100000", "lastPrice": 0}},
    )

    assert await collector.collect_once() == 0
    assert collector.health()["lastErrorCode"] == "QMT_REALTIME_INVALID_PAYLOAD"


@pytest.mark.asyncio
async def test_collector_reports_missing_owner_without_queue_growth():
    gateway = QmtCommandGateway()
    errors = []
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=lambda _quote: None,
        error_publisher=lambda code, message: errors.append((code, message)),
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])

    assert await collector.collect_once() == 0
    assert gateway.health()["pendingCount"] == 0
    assert collector.health()["lastErrorCode"] == "QMT_BRIDGE_OWNER_MISSING"
    assert errors == [("QMT_BRIDGE_OWNER_MISSING", "QMT bridge owner is not ready")]


@pytest.mark.asyncio
async def test_collector_expires_and_consumes_timed_out_command():
    monotonic = [0.0]
    gateway = QmtCommandGateway(
        clock=lambda: monotonic[0],
        default_timeout_seconds=1.0,
    )
    gateway.register_owner("owner")
    collector = QmtRealtimeCollector(
        gateway=gateway,
        publisher=lambda _quote: None,
        now=lambda: datetime(2026, 7, 14, 10, 0, tzinfo=BEIJING),
    )
    collector.sync_subscriptions(["600030.SH"])

    await collector.collect_once()
    gateway.poll("owner")
    monotonic[0] = 2.0

    assert await collector.collect_once() == 0
    assert collector.health()["inFlight"] is False
    assert collector.health()["lastErrorCode"] == "QMT_COMMAND_TIMEOUT"
    assert gateway.health()["resultCount"] == 0
