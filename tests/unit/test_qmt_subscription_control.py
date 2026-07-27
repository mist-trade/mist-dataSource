import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from src.datasource.qmt.realtime import subscription as subscription_module
from src.datasource.qmt.realtime.subscription import (
    QmtNativeReply,
    QmtSubscriptionControlError,
    QmtSubscriptionController,
    QmtSubscriptionJournal,
    QmtSubscriptionJournalError,
    QmtSubscriptionSequenceError,
    QmtWholeSubscription,
    configured_qmt_unsubscribe_success_values,
)


def _journal(tmp_path: Path) -> QmtSubscriptionJournal:
    return QmtSubscriptionJournal(
        path=tmp_path / "subscription-journal.jsonl",
        rotate_bytes=262_144,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )


def _controller(
    tmp_path: Path,
    *,
    timeout_seconds: float = 1.0,
) -> tuple[QmtSubscriptionController, list[dict[str, Any]]]:
    published: list[dict[str, Any]] = []
    controller = QmtSubscriptionController(
        journal=_journal(tmp_path),
        owner_validator=lambda _owner, _token, _generation: None,
        publisher=published.append,
        unsubscribe_success_values=frozenset({0}),
        timeout_seconds=timeout_seconds,
    )
    return controller, published


async def _wait_for_slot(controller: QmtSubscriptionController) -> None:
    for _ in range(100):
        if controller.health()["inFlight"]:
            return
        await asyncio.sleep(0)
    raise AssertionError("subscription native-call slot was not created")


def _fail_journal_kind(
    monkeypatch: pytest.MonkeyPatch,
    journal: QmtSubscriptionJournal,
    failed_kind: str,
) -> None:
    original_append = journal.append

    def append(kind: str, detail: dict[str, Any]) -> dict[str, Any]:
        if kind == failed_kind:
            journal.healthy = False
            journal.last_error = f"injected {failed_kind} durability failure"
            raise QmtSubscriptionJournalError(journal.last_error)
        return original_append(kind, detail)

    monkeypatch.setattr(journal, "append", append)


@pytest.mark.asyncio
@pytest.mark.parametrize("sub_id", [0, -7, 23])
async def test_single_subscribe_accepts_every_exact_integer_id(
    tmp_path: Path,
    sub_id: int,
) -> None:
    controller, _ = _controller(tmp_path)
    task = asyncio.create_task(controller.execute("subscribe", symbol="300502.SZ"))
    await _wait_for_slot(controller)

    command = controller.poll_command("owner", "token", 1)
    assert command == {
        "callSequence": 1,
        "method": "subscribe_quote",
        "symbol": "300502.SZ",
    }
    assert controller.poll_command("owner", "token", 1) is None
    controller.post_result(
        "owner",
        "token",
        1,
        1,
        QmtNativeReply(success_present=True, success=sub_id, failure=None),
    )

    assert await task == ("subscribed", {"success": sub_id})
    assert controller.registry.public_value() == {
        "whole": None,
        "singles": {"300502.SZ": sub_id},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", [True, 1.0, "1", None])
async def test_subscribe_rejects_non_exact_integer_result(
    tmp_path: Path,
    invalid: Any,
) -> None:
    controller, _ = _controller(tmp_path)
    task = asyncio.create_task(controller.execute("subscribe", symbol="300502.SZ"))
    await _wait_for_slot(controller)
    command = controller.poll_command("owner", "token", 1)
    assert command is not None
    controller.post_result(
        "owner",
        "token",
        1,
        command["callSequence"],
        QmtNativeReply(success_present=True, success=invalid, failure=None),
    )

    assert await task == (
        "subscribed",
        {
            "failure": {
                "symbol": "300502.SZ",
                "reason": "QMT_INVALID_SUBSCRIPTION_ID",
            }
        },
    )
    assert controller.registry.public_value()["singles"] == {}


@pytest.mark.asyncio
async def test_whole_member_individual_unsubscribe_is_rejected_without_native_call(
    tmp_path: Path,
) -> None:
    controller, _ = _controller(tmp_path)
    controller.registry.whole = QmtWholeSubscription(10, ("300502.SZ",))

    result = await controller.execute("unsubscribe", symbol="300502.SZ")

    assert result == (
        "unsubscribed",
        {
            "failure": {
                "symbol": "300502.SZ",
                "reason": "QMT_SYMBOL_OWNED_BY_WHOLE",
                "subscriptionState": "subscribed",
            }
        },
    )
    assert controller.health()["inFlight"] is False


@pytest.mark.asyncio
async def test_sync_cancels_whole_then_sorted_singles_and_creates_exact_whole(
    tmp_path: Path,
) -> None:
    controller, _ = _controller(tmp_path)
    controller.registry.whole = QmtWholeSubscription(10, ("600030.SH",))
    controller.registry.singles = {"600519.SH": 12, "000001.SZ": 11}
    task = asyncio.create_task(
        controller.execute(
            "sync_subscriptions",
            symbols=["300502.SZ", "000001.SZ", "300502.SZ"],
        )
    )

    expected = [
        {
            "callSequence": 1,
            "method": "unsubscribe_quote",
            "subId": 10,
            "symbol": None,
        },
        {
            "callSequence": 2,
            "method": "unsubscribe_quote",
            "subId": 11,
            "symbol": "000001.SZ",
        },
        {
            "callSequence": 3,
            "method": "unsubscribe_quote",
            "subId": 12,
            "symbol": "600519.SH",
        },
        {
            "callSequence": 4,
            "method": "subscribe_whole_quote",
            "symbols": ["000001.SZ", "300502.SZ"],
        },
    ]
    for command_expected in expected:
        await _wait_for_slot(controller)
        command = controller.poll_command("owner", "token", 1)
        assert command == command_expected
        result = 99 if command["method"] == "subscribe_whole_quote" else 0
        controller.post_result(
            "owner",
            "token",
            1,
            command["callSequence"],
            QmtNativeReply(success_present=True, success=result, failure=None),
        )
        await asyncio.sleep(0)

    assert await task == ("subscriptions_synced", {"success": 99})
    assert controller.registry.public_value() == {
        "whole": {
            "subId": 99,
            "symbols": ["000001.SZ", "300502.SZ"],
        },
        "singles": {},
    }


@pytest.mark.asyncio
async def test_late_result_cannot_complete_a_newer_slot(tmp_path: Path) -> None:
    controller, _ = _controller(tmp_path, timeout_seconds=0.01)
    first = asyncio.create_task(controller.execute("subscribe", symbol="300502.SZ"))
    await _wait_for_slot(controller)
    first_command = controller.poll_command("owner", "token", 1)
    assert first_command is not None
    first_result = await first
    assert first_result[1]["failure"]["reason"] == "QMT_SUBSCRIPTION_CALL_TIMEOUT"

    second = asyncio.create_task(controller.execute("subscribe", symbol="600030.SH"))
    await _wait_for_slot(controller)
    second_command = controller.poll_command("owner", "token", 1)
    assert second_command is not None
    assert second_command["callSequence"] > first_command["callSequence"]

    with pytest.raises(QmtSubscriptionSequenceError):
        controller.post_result(
            "owner",
            "token",
            1,
            first_command["callSequence"],
            QmtNativeReply(success_present=True, success=1, failure=None),
        )
    assert controller.health()["inFlight"] is True

    controller.post_result(
        "owner",
        "token",
        1,
        second_command["callSequence"],
        QmtNativeReply(success_present=True, success=2, failure=None),
    )
    assert await second == ("subscribed", {"success": 2})


@pytest.mark.asyncio
async def test_intent_durability_failure_exposes_no_native_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, _ = _controller(tmp_path)
    _fail_journal_kind(monkeypatch, controller.journal, "native_intent")

    assert await controller.execute("subscribe", symbol="300502.SZ") == (
        "subscribed",
        {
            "failure": {
                "symbol": "300502.SZ",
                "reason": "QMT_JOURNAL_DURABILITY_FAILED",
            }
        },
    )
    assert controller.poll_command("owner", "token", 1) is None
    assert controller.health()["callSequence"] == 0
    assert controller.health()["inFlight"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_kind", ["native_result", "registry_transition"])
async def test_subscribe_durability_failure_retains_id_and_blocks_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_kind: str,
) -> None:
    controller, published = _controller(tmp_path)
    _fail_journal_kind(monkeypatch, controller.journal, failed_kind)

    task = asyncio.create_task(controller.execute("subscribe", symbol="300502.SZ"))
    await _wait_for_slot(controller)
    command = controller.poll_command("owner", "token", 1)
    assert command is not None
    controller.post_result(
        "owner",
        "token",
        1,
        command["callSequence"],
        QmtNativeReply(success_present=True, success=123, failure=None),
    )

    assert await task == (
        "subscribed",
        {
            "failure": {
                "symbol": "300502.SZ",
                "reason": "QMT_JOURNAL_DURABILITY_FAILED",
            }
        },
    )
    assert controller.registry.public_value()["singles"] == {"300502.SZ": 123}
    assert controller.registry.retained_recovery == {("single", "300502.SZ", 123)}
    assert controller.health()["reconciliationRequired"] is True
    assert controller.health()["retainedRecoveryCount"] == 1

    snapshot = await controller.accept_snapshot(
        "owner",
        "token",
        1,
        123,
        "2026-07-26T10:00:00+08:00",
        {"300502.SZ": {"lastPrice": 10.5}},
    )
    assert snapshot == {
        "accepted": [],
        "rejected": [
            {"symbol": "300502.SZ", "reason": "QMT_SNAPSHOT_NON_MEMBER"}
        ],
    }
    assert published == []
    assert await controller.execute("subscribe", symbol="600030.SH") == (
        "subscribed",
        {
            "failure": {
                "symbol": "600030.SH",
                "reason": "QMT_JOURNAL_RECONCILIATION_REQUIRED",
            }
        },
    )
    assert controller.poll_command("owner", "token", 1) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_kind", ["native_result", "registry_transition"])
async def test_confirmed_unsubscribe_durability_failure_retains_original_bucket(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_kind: str,
) -> None:
    controller, _ = _controller(tmp_path)
    controller.registry.singles["300502.SZ"] = 123
    _fail_journal_kind(monkeypatch, controller.journal, failed_kind)

    task = asyncio.create_task(controller.execute("unsubscribe", symbol="300502.SZ"))
    await _wait_for_slot(controller)
    command = controller.poll_command("owner", "token", 1)
    assert command is not None
    controller.post_result(
        "owner",
        "token",
        1,
        command["callSequence"],
        QmtNativeReply(success_present=True, success=0, failure=None),
    )

    assert await task == (
        "unsubscribed",
        {
            "failure": {
                "symbol": "300502.SZ",
                "reason": "QMT_JOURNAL_DURABILITY_FAILED",
                "subscriptionState": "unknown",
            }
        },
    )
    assert controller.registry.public_value()["singles"] == {"300502.SZ": 123}
    assert controller.registry.retained_recovery == {("single", "300502.SZ", 123)}
    assert controller.health()["reconciliationRequired"] is True
    assert await controller.execute("sync_subscriptions", symbols=["600030.SH"]) == (
        "subscriptions_synced",
        {
            "failure": {
                "symbol": None,
                "reason": "QMT_JOURNAL_RECONCILIATION_REQUIRED",
            }
        },
    )
    assert controller.poll_command("owner", "token", 1) is None


@pytest.mark.asyncio
async def test_snapshot_checks_handle_membership_per_code(tmp_path: Path) -> None:
    controller, published = _controller(tmp_path)
    controller.registry.singles["300502.SZ"] = 7

    result = await controller.accept_snapshot(
        "owner",
        "token",
        1,
        7,
        "2026-07-26T10:00:00+08:00",
        {
            "300502.SZ": {"lastPrice": 10.5},
            "600030.SH": {"lastPrice": 20.5},
            "not-a-symbol": {"lastPrice": 1},
        },
    )

    assert result == {
        "accepted": ["300502.SZ"],
        "rejected": [
            {"symbol": "600030.SH", "reason": "QMT_SNAPSHOT_NON_MEMBER"},
            {"symbol": "NOT-A-SYMBOL", "reason": "QMT_SNAPSHOT_SYMBOL_INVALID"},
        ],
    }
    assert published == [
        {
            "schemaVersion": 2,
            "capturedAt": "2026-07-26T10:00:00+08:00",
            "native": {"300502.SZ": {"lastPrice": 10.5}},
        }
    ]

    with pytest.raises(QmtSubscriptionControlError) as exc_info:
        await controller.accept_snapshot(
            "owner",
            "token",
            1,
            7,
            "2026-07-26T10:00:00",
            {"300502.SZ": {"lastPrice": 10.5}},
        )
    assert exc_info.value.reason == "QMT_SNAPSHOT_CAPTURED_AT_INVALID"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rotate_bytes", 0),
        ("rotate_bytes", True),
        ("rotate_bytes", "1.5"),
        ("archive_max_bytes", 262_143),
        ("resolved_retention_days", -1),
    ],
)
def test_journal_rejects_invalid_bounded_configuration(
    tmp_path: Path,
    field: str,
    value: Any,
) -> None:
    kwargs: dict[str, Any] = {
        "path": tmp_path / "journal.jsonl",
        "rotate_bytes": 262_144,
        "archive_max_bytes": 524_288,
        "resolved_retention_days": 90,
    }
    kwargs[field] = value

    with pytest.raises(ValueError):
        QmtSubscriptionJournal(**kwargs)


def test_journal_rotation_is_reloadable_and_archive_tamper_fails_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.jsonl"
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    detail = {f"field{index}": "x" * 1000 for index in range(45)}
    for index in range(4):
        journal.append("test_record", {"index": index, **detail})

    archives = sorted(tmp_path.glob("journal.jsonl.*.*.jsonl"))
    assert archives
    assert archives[0].with_suffix(".jsonl.sha256").exists()
    reloaded = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    assert reloaded.healthy is True
    assert reloaded.health()["archiveBytes"] > 0

    archive = archives[0]
    archive.write_bytes(archive.read_bytes() + b" ")
    with pytest.raises(QmtSubscriptionJournalError):
        QmtSubscriptionJournal(
            path=path,
            rotate_bytes=131_072,
            archive_max_bytes=524_288,
            resolved_retention_days=90,
        )


@pytest.mark.parametrize(
    "boundary",
    [
        "active_to_rotating",
        "rotating_to_archive",
        "manifest_published",
        "anchor_published",
    ],
)
def test_journal_recovers_each_interrupted_rotation_publish_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    path = tmp_path / "journal.jsonl"
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    filler = {f"field{index}": "x" * 1000 for index in range(45)}
    journal.append("before_rotation", {"index": 0, **filler})
    journal.append("before_rotation", {"index": 1, **filler})

    original_replace = subscription_module._durable_replace
    original_json_write = subscription_module._atomic_json_write
    original_bytes_write = subscription_module._atomic_bytes_write

    def interrupted_replace(source: Path, target: Path) -> None:
        original_replace(source, target)
        if (
            boundary == "active_to_rotating"
            and target.name == "journal.jsonl.rotating"
        ) or (
            boundary == "rotating_to_archive"
            and target.name.endswith(".jsonl")
            and target.name != "journal.jsonl"
        ):
            raise OSError("injected rotation interruption")

    def interrupted_json_write(path_value: Path, value: dict[str, Any]) -> None:
        original_json_write(path_value, value)
        if boundary == "manifest_published" and path_value.name.endswith(
            ".manifest.json"
        ):
            raise OSError("injected rotation interruption")

    def interrupted_bytes_write(path_value: Path, value: bytes) -> None:
        original_bytes_write(path_value, value)
        if boundary == "anchor_published" and path_value == path:
            raise OSError("injected rotation interruption")

    monkeypatch.setattr(subscription_module, "_durable_replace", interrupted_replace)
    monkeypatch.setattr(subscription_module, "_atomic_json_write", interrupted_json_write)
    monkeypatch.setattr(subscription_module, "_atomic_bytes_write", interrupted_bytes_write)
    with pytest.raises(
        QmtSubscriptionJournalError,
        match="injected rotation interruption",
    ):
        journal.append("trigger_rotation", {"index": 2, **filler})
    monkeypatch.undo()

    recovered = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    assert recovered.healthy is True
    sequence_before = recovered.record_sequence
    recovered.append("after_recovery", {"boundary": boundary})
    assert recovered.record_sequence == sequence_before + 1
    assert not (tmp_path / "journal.jsonl.rotating").exists()
    assert not (tmp_path / "journal.jsonl.tmp").exists()


def test_journal_compacts_only_resolved_lifecycle_prefix_and_reloads(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.jsonl"
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    filler = {f"field{index}": "x" * 1000 for index in range(45)}
    journal.append(
        "native_intent",
        {"callSequence": 1, "method": "subscribe_quote", "symbol": "300502.SZ"},
    )
    journal.append(
        "native_result",
        {
            "callSequence": 1,
            "method": "subscribe_quote",
            "successPresent": True,
            "success": 123,
            "failure": None,
        },
    )
    journal.append(
        "registry_transition",
        {"transition": "single_subscribed", "symbol": "300502.SZ", "subId": 123},
    )
    journal.append(
        "native_intent",
        {
            "callSequence": 2,
            "method": "unsubscribe_quote",
            "symbol": "300502.SZ",
            "subId": 123,
        },
    )
    journal.append(
        "native_result",
        {
            "callSequence": 2,
            "method": "unsubscribe_quote",
            "successPresent": True,
            "success": 0,
            "failure": None,
        },
    )
    journal.append(
        "registry_transition",
        {
            "transition": "unsubscribed",
            "bucket": "single",
            "symbol": "300502.SZ",
            "subId": 123,
        },
    )
    for index in range(6):
        journal.append("resolved_evidence", {"index": index, **filler})

    sequence_before = journal.record_sequence
    assert journal.compact() is True
    checkpoints = list(tmp_path.glob("journal.jsonl.compaction-checkpoint.*.json"))
    assert checkpoints
    checkpoint = json.loads(checkpoints[0].read_text(encoding="utf-8"))
    assert checkpoint["resolvedLifecycles"] == [
        {
            "bucket": "single",
            "firstSequence": 3,
            "lastSequence": 6,
            "subId": 123,
            "symbol": "300502.SZ",
            "terminal": "unsubscribed",
            "terminalArchiveSha256": checkpoint["resolvedLifecycles"][0][
                "terminalArchiveSha256"
            ],
            "terminalRecordHash": checkpoint["resolvedLifecycles"][0]["terminalRecordHash"],
        }
    ]
    assert list(tmp_path.glob("journal.jsonl.*.*.jsonl")) == []

    reloaded = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    assert reloaded.record_sequence == sequence_before
    reloaded.append("after_compaction", {"ok": True})
    assert reloaded.record_sequence == sequence_before + 1


def test_journal_compaction_pins_unresolved_handle(tmp_path: Path) -> None:
    path = tmp_path / "journal.jsonl"
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    filler = {f"field{index}": "x" * 1000 for index in range(45)}
    journal.append(
        "native_intent",
        {"callSequence": 1, "method": "subscribe_quote", "symbol": "300502.SZ"},
    )
    journal.append(
        "native_result",
        {
            "callSequence": 1,
            "method": "subscribe_quote",
            "successPresent": True,
            "success": 123,
            "failure": None,
        },
    )
    journal.append(
        "registry_transition",
        {"transition": "single_subscribed", "symbol": "300502.SZ", "subId": 123},
    )
    for index in range(5):
        journal.append("unresolved_evidence", {"index": index, **filler})

    archives_before = list(tmp_path.glob("journal.jsonl.*.*.jsonl"))
    assert archives_before
    assert journal.compact() is False
    assert list(tmp_path.glob("journal.jsonl.*.*.jsonl")) == archives_before


@pytest.mark.parametrize(
    "boundary",
    [
        "prepared",
        "checkpoint",
        "checkpoint_published",
        "catalog_published",
        "source_retired",
    ],
)
def test_journal_recovers_each_interrupted_compaction_publish_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    path = tmp_path / "journal.jsonl"
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    filler = {f"field{index}": "x" * 1000 for index in range(45)}
    for index in range(6):
        journal.append("resolved_evidence", {"index": index, **filler})
    archive = sorted(tmp_path.glob("journal.jsonl.*.*.jsonl"))[0]
    original_json_write = subscription_module._atomic_json_write
    original_unlink = Path.unlink
    failed = False

    def interrupted_json_write(path_value: Path, value: dict[str, Any]) -> None:
        nonlocal failed
        original_json_write(path_value, value)
        is_target = (
            boundary == "prepared"
            and path_value.name.endswith(".maintenance.json")
            and value.get("phase") == "prepared"
        ) or (
            boundary == "checkpoint"
            and ".compaction-checkpoint." in path_value.name
        ) or (
            boundary == "checkpoint_published"
            and path_value.name.endswith(".maintenance.json")
            and value.get("phase") == "checkpoint_published"
        ) or (
            boundary == "catalog_published"
            and path_value.name.endswith(".catalog.json")
        )
        if is_target and not failed:
            failed = True
            raise OSError("injected compaction interruption")

    def interrupted_unlink(target: Path, *args: Any, **kwargs: Any) -> None:
        nonlocal failed
        original_unlink(target, *args, **kwargs)
        if boundary == "source_retired" and target == archive and not failed:
            failed = True
            raise OSError("injected compaction interruption")

    monkeypatch.setattr(subscription_module, "_atomic_json_write", interrupted_json_write)
    monkeypatch.setattr(Path, "unlink", interrupted_unlink)
    with pytest.raises(OSError, match="injected compaction interruption"):
        journal.compact()
    monkeypatch.undo()

    recovered = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    assert recovered.healthy is True
    assert not (tmp_path / "journal.jsonl.maintenance.json").exists()
    assert archive.exists() is (boundary == "prepared")


def test_journal_folds_expired_resolved_checkpoints_with_deterministic_clock(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 1, 1, tzinfo=UTC)]
    path = tmp_path / "journal.jsonl"
    journal = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=131_072,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
        wall_clock=lambda: now[0],
    )
    filler = {f"field{index}": "x" * 1000 for index in range(45)}
    for cycle in range(2):
        for index in range(6):
            journal.append(
                "resolved_evidence",
                {"cycle": cycle, "index": index, **filler},
            )
        assert journal.compact() is True
        if cycle == 0:
            now[0] += timedelta(days=91)

    folds = list(tmp_path.glob("journal.jsonl.compaction-fold.*.json"))
    assert len(folds) == 1
    fold = json.loads(folds[0].read_text(encoding="utf-8"))
    assert fold["kind"] == "resolved_lifecycle_fold"
    assert len(fold["sealedRootSha256"]) == 64
    assert "retiredCheckpointDigests" not in fold
    assert len(list(tmp_path.glob("journal.jsonl.compaction-checkpoint.*.json"))) == 1


@pytest.mark.asyncio
async def test_control_health_exposes_bounded_metric_dimensions(
    tmp_path: Path,
) -> None:
    controller, _ = _controller(tmp_path)
    assert await controller.execute("get_subscriptions") == (
        "subscriptions",
        {"success": {"whole": None, "singles": {}}},
    )
    assert controller.health()["controlTotals"] == [
        {
            "operation": "get_subscriptions",
            "result": "success",
            "reason": "none",
            "value": 1,
        }
    ]


def test_unsubscribe_success_values_are_explicit_hil_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MIST_QMT_UNSUBSCRIBE_SUCCESS_VALUES", raising=False)
    assert configured_qmt_unsubscribe_success_values() == frozenset()

    monkeypatch.setenv("MIST_QMT_UNSUBSCRIBE_SUCCESS_VALUES", "0,-1, 7")
    assert configured_qmt_unsubscribe_success_values() == frozenset({0, -1, 7})

    monkeypatch.setenv("MIST_QMT_UNSUBSCRIBE_SUCCESS_VALUES", "0,true")
    with pytest.raises(ValueError):
        configured_qmt_unsubscribe_success_values()


@pytest.mark.asyncio
async def test_restart_requires_durable_operator_context_rebuild_observation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "journal.jsonl"
    first = QmtSubscriptionJournal(
        path=path,
        rotate_bytes=262_144,
        archive_max_bytes=524_288,
        resolved_retention_days=90,
    )
    first.append("subscribe_result", {"subId": 123})
    restarted = QmtSubscriptionController(
        journal=QmtSubscriptionJournal(
            path=path,
            rotate_bytes=262_144,
            archive_max_bytes=524_288,
            resolved_retention_days=90,
        ),
        owner_validator=lambda _owner, _token, _generation: None,
        publisher=lambda _frame: None,
    )

    assert await restarted.execute("sync_subscriptions", symbols=[]) == (
        "subscriptions_synced",
        {
            "failure": {
                "symbol": None,
                "reason": "QMT_JOURNAL_RECONCILIATION_REQUIRED",
            }
        },
    )
    restarted.observe_rebuilt_context()
    assert restarted.health()["reconciliationRequired"] is False
    assert await restarted.execute("get_subscriptions") == (
        "subscriptions",
        {"success": {"whole": None, "singles": {}}},
    )
