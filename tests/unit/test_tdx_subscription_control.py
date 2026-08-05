from __future__ import annotations

import asyncio
from contextlib import suppress

from src.datasource.tdx.realtime.gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_SCHEMA_VERSION,
    TdxRealtimeGateway,
)


async def _register(gateway: TdxRealtimeGateway) -> None:
    await gateway.register_owner(
        owner_id="tdx-test",
        bridge_build_id="test-build",
        bridge_artifact_sha256="test-sha",
        acquisition_profile=ACCEPTED_ACQUISITION_PROFILE,
        schema_version=ACCEPTED_SCHEMA_VERSION,
    )

async def test_get_subscriptions_returns_bridge_observed_native_list() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    read_task = asyncio.create_task(gateway.execute_control("get_subscriptions"))
    await asyncio.sleep(0)
    owner = gateway.owner
    assert owner is not None
    poll = await gateway.poll(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
    )
    assert poll["nativeProbeRevision"] == 1
    await gateway.post_result(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
        desired_revision=0,
        applied_revision=0,
        active=["SH600519", "600519.SH", "000001.SZ"],
        rejected=[],
        native_probe_revision=poll["nativeProbeRevision"],
    )
    response_type, data = await read_task
    assert response_type == "subscriptions"
    assert data == {"success": ["000001.SZ", "600519.SH"]}

async def test_get_subscriptions_rejects_cached_list_without_fresh_native_probe() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.01)
    await _register(gateway)
    gateway._last_reported_active = {"600519.SH"}

    assert await gateway.execute_control("get_subscriptions") == (
        "subscriptions",
        {
            "failure": {
                "symbol": None,
                "reason": "TDX_SUBSCRIPTIONS_READ_FAILED",
            }
        },
    )

async def test_unsubscribe_changes_desired_then_waits_for_bridge_native_result() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    await gateway.sync_desired(["600519.SH"])
    task = asyncio.create_task(gateway.execute_control(
        "unsubscribe",
        symbol="SH600519",
    ))
    await asyncio.sleep(0)
    owner = gateway.owner
    assert owner is not None
    revision = gateway._desired_revision
    await gateway.post_result(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
        desired_revision=revision,
        applied_revision=revision,
        active=[],
        rejected=[],
    )
    response_type, data = await task
    assert response_type == "unsubscribed"
    assert data == {"success": None}
    assert gateway.desired_symbols == []

async def test_unsubscribe_failure_does_not_restore_old_desired() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.01)
    await _register(gateway)
    await gateway.sync_desired(["600519.SH"])
    gateway._last_reported_active = {"600519.SH"}
    _, data = await gateway.execute_control("unsubscribe", symbol="600519.SH")
    assert data == {
        "failure": {
            "symbol": "600519.SH",
            "reason": "TDX_UNSUBSCRIBE_NOT_CONVERGED",
            "subscriptionState": "subscribed",
        }
    }
    assert gateway.desired_symbols == []

async def test_subscribe_waits_for_bridge_convergence() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    task = asyncio.create_task(
        gateway.execute_control("subscribe", symbol="SH600519")
    )
    await asyncio.sleep(0)
    owner = gateway.owner
    assert owner is not None
    revision = gateway._desired_revision
    await gateway.post_result(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
        desired_revision=revision,
        applied_revision=revision,
        active=["600519.SH"],
        rejected=[],
    )
    assert await task == ("subscribed", {"success": None})

async def test_sync_clears_extras_then_waits_for_exact_bridge_target() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    gateway._last_reported_active = {"000001.SZ"}
    task = asyncio.create_task(
        gateway.execute_control(
            "sync_subscriptions",
            symbols=["SH600519"],
        )
    )
    await asyncio.sleep(0)
    owner = gateway.owner
    assert owner is not None
    revision = gateway._desired_revision
    await gateway.post_result(
        lease_token=owner.lease_token,
        stream_epoch=owner.stream_epoch,
        desired_revision=revision,
        applied_revision=revision,
        active=["600519.SH"],
        rejected=[],
    )
    assert await task == ("subscriptions_synced", {"success": None})

async def test_second_tdx_mutation_fails_busy_without_queueing() -> None:
    gateway = TdxRealtimeGateway(control_timeout_seconds=0.5)
    await _register(gateway)
    first = asyncio.create_task(
        gateway.execute_control("subscribe", symbol="600519.SH")
    )
    await asyncio.sleep(0)

    assert await gateway.execute_control("subscribe", symbol="000001.SZ") == (
        "subscribed",
        {
            "failure": {
                "symbol": "000001.SZ",
                "reason": "TDX_SUBSCRIPTION_CONTROL_BUSY",
            }
        },
    )
    first.cancel()
    with suppress(asyncio.CancelledError):
        await first

