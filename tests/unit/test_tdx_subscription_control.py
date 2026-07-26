from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from src.datasource.tdx.realtime.runtime import (
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


def test_get_subscriptions_returns_normalized_official_list() -> None:
    async def run() -> None:
        async def rpc(method: str, params: dict[str, Any]) -> Any:
            assert method == "get_subscribe_hq_stock_list"
            assert params == {}
            return ["SH600519", "600519.SH", "000001.SZ"]

        gateway = TdxRealtimeGateway(rpc_call=rpc)
        response_type, data = await gateway.execute_control("get_subscriptions")
        assert response_type == "subscriptions"
        assert data == {"success": ["600519.SH", "000001.SZ"]}

    asyncio.run(run())


def test_unsubscribe_changes_desired_before_official_http_and_verifies_list() -> None:
    async def run() -> None:
        active = {"600519.SH"}
        calls: list[str] = []
        gateway: TdxRealtimeGateway

        async def rpc(method: str, params: dict[str, Any]) -> Any:
            calls.append(method)
            assert "600519.SH" not in gateway.desired_symbols
            if method == "get_subscribe_hq_stock_list":
                return sorted(active)
            assert method == "unsubscribe_hq"
            assert params == {"stock_list": ["600519.SH"]}
            active.discard("600519.SH")
            return {"ErrorId": "unexpected-but-ignored"}

        gateway = TdxRealtimeGateway(rpc_call=rpc)
        await gateway.sync_desired(["600519.SH"])
        response_type, data = await gateway.execute_control(
            "unsubscribe",
            symbol="SH600519",
        )
        assert response_type == "unsubscribed"
        assert data == {"success": None}
        assert calls == [
            "get_subscribe_hq_stock_list",
            "unsubscribe_hq",
            "get_subscribe_hq_stock_list",
        ]
        assert gateway.desired_symbols == []

    asyncio.run(run())


def test_unsubscribe_failure_does_not_restore_old_desired() -> None:
    async def run() -> None:
        async def rpc(method: str, _params: dict[str, Any]) -> Any:
            if method == "get_subscribe_hq_stock_list":
                return ["600519.SH"]
            raise RuntimeError("provider cancellation failed")

        gateway = TdxRealtimeGateway(rpc_call=rpc)
        await gateway.sync_desired(["600519.SH"])
        _, data = await gateway.execute_control("unsubscribe", symbol="600519.SH")
        assert data == {
            "failure": {
                "symbol": "600519.SH",
                "reason": "TDX_UNSUBSCRIBE_NOT_CONVERGED",
                "subscriptionState": "subscribed",
            }
        }
        assert gateway.desired_symbols == []

    asyncio.run(run())


def test_subscribe_waits_for_bridge_convergence() -> None:
    async def run() -> None:
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

    asyncio.run(run())


def test_sync_clears_extras_then_waits_for_exact_bridge_target() -> None:
    async def run() -> None:
        active = {"000001.SZ"}

        async def rpc(method: str, params: dict[str, Any]) -> Any:
            if method == "get_subscribe_hq_stock_list":
                return sorted(active)
            assert method == "unsubscribe_hq"
            active.difference_update(params["stock_list"])
            return None

        gateway = TdxRealtimeGateway(rpc_call=rpc, control_timeout_seconds=0.5)
        await _register(gateway)
        task = asyncio.create_task(
            gateway.execute_control(
                "sync_subscriptions",
                symbols=["SH600519"],
            )
        )
        for _ in range(20):
            if gateway.desired_symbols == ["600519.SH"] and not active:
                break
            await asyncio.sleep(0)
        active.add("600519.SH")
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

    asyncio.run(run())


def test_second_tdx_mutation_fails_busy_without_queueing() -> None:
    async def run() -> None:
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

    asyncio.run(run())
