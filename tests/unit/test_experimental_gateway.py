"""Unit tests for the experimental TDX realtime gateway state machine."""

from __future__ import annotations

import asyncio

import pytest

from src.datasource.tdx.experimental_gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_DRAFT_REVISION,
    ACCEPTED_SCHEMA_VERSION,
    ExperimentalTdxRealtimeGateway,
    GatewayError,
)

CONTRACT_KWARGS = {
    "acquisition_profile": ACCEPTED_ACQUISITION_PROFILE,
    "schema_version": ACCEPTED_SCHEMA_VERSION,
    "draft_revision": ACCEPTED_DRAFT_REVISION,
}


def _native_snapshot() -> dict[str, object]:
    return {
        "Now": "1685.0",
        "Open": "1670.0",
        "Max": "1690.0",
        "Min": "1665.0",
        "LastClose": "1672.5",
        "Volume": "12345600",
        "Amount": "20800000000",
        "AsOf": "2026-07-16T14:30:00.000+08:00",
        "Code": "600519.SH",
        "ErrorId": "0",
    }


@pytest.fixture()
def gateway() -> ExperimentalTdxRealtimeGateway:
    return ExperimentalTdxRealtimeGateway(max_subscriptions=100)


@pytest.fixture()
def async_loop() -> asyncio.AbstractEventLoop:
    return asyncio.new_event_loop()


class TestOwnerRegistration:
    def test_register_returns_lease_and_epoch(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        result = async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-1",
                bridge_build_id="sha-abc",
                bridge_artifact_sha256="9f2c",
                **CONTRACT_KWARGS,
            )
        )
        assert "leaseToken" in result
        assert "streamEpoch" in result
        assert result["acceptedContractTuple"]["payloadType"] == "tdx.realtime.snapshot"

    def test_contract_mismatch_rejected(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        with pytest.raises(GatewayError) as exc_info:
            async_loop.run_until_complete(
                gateway.register_owner(
                    owner_id="bridge-1",
                    bridge_build_id="sha",
                    bridge_artifact_sha256="9f2c",
                    acquisition_profile="wrong",
                    schema_version=0,
                    draft_revision=1,
                )
            )
        assert exc_info.value.code == "TDX_BRIDGE_CONTRACT_MISMATCH"

    def test_new_generation_creates_new_epoch(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        r1 = async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-1",
                bridge_build_id="sha",
                bridge_artifact_sha256="9f2c",
                **CONTRACT_KWARGS,
            )
        )
        r2 = async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-1",
                bridge_build_id="sha",
                bridge_artifact_sha256="9f2c",
                **CONTRACT_KWARGS,
            )
        )
        assert r1["streamEpoch"] != r2["streamEpoch"]


class TestSubscriptionConvergence:
    def test_converged_after_clean_reconcile(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH"])
            # Report result: active == desired, no rejections.
            res = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            assert res["converged"] is True
            assert gateway.converged_revision == rev

        async_loop.run_until_complete(run())

    def test_not_converged_with_rejections(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH"])
            res = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=[],
                rejected=[{"symbol": "600519.SH", "reason": "denied"}],
            )
            assert res["converged"] is False

        async_loop.run_until_complete(run())

    def test_not_converged_when_active_differs_from_desired(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH", "000001.SZ"])
            res = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],  # missing 000001.SZ
                rejected=[],
            )
            assert res["converged"] is False

        async_loop.run_until_complete(run())


class TestSnapshotAcceptance:
    def test_accepts_converged_symbol_with_monotonic_sequence(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH"])
            await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            r1 = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                symbol="600519.SH",
                producer_sequence=1,
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            assert r1["accepted"] is True
            assert r1["sequence"] == 1
            r2 = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                symbol="600519.SH",
                producer_sequence=2,
                captured_at="2026-07-16T14:30:02.000+08:00",
                native=_native_snapshot(),
            )
            assert r2["sequence"] == 2

        async_loop.run_until_complete(run())

    def test_rejects_duplicate_producer_sequence(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        """HTTP retry with same producer_sequence must NOT re-broadcast."""

        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH"])
            await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                symbol="600519.SH",
                producer_sequence=7,
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            # Retry same producer_sequence=7 → must be rejected (not re-broadcast).
            with pytest.raises(GatewayError) as exc_info:
                await gateway.post_snapshot(
                    lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                    symbol="600519.SH",
                    producer_sequence=7,
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_DUPLICATE_PRODUCER_SEQUENCE"

        async_loop.run_until_complete(run())

    def test_rejects_non_rfc3339_captured_at(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        """Non-RFC3339 capturedAt must be rejected."""

        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH"])
            await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            with pytest.raises(GatewayError) as exc_info:
                await gateway.post_snapshot(
                    lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                    symbol="600519.SH",
                    producer_sequence=1,
                    captured_at="not-a-timestamp",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_INVALID_TIMESTAMP"

        async_loop.run_until_complete(run())

        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            await gateway.sync_desired(["600519.SH"])
            # Don't report convergence.
            with pytest.raises(GatewayError) as exc_info:
                await gateway.post_snapshot(
                    lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                    symbol="600519.SH",
                    producer_sequence=1,
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_SYMBOL_NOT_CONVERGED"

        async_loop.run_until_complete(run())

    def test_invalid_lease_rejected(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            with pytest.raises(GatewayError) as exc_info:
                await gateway.post_snapshot(
                    lease_token="wrong-token",
                    symbol="600519.SH",
                    producer_sequence=1,
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_LEASE_INVALID"

        async_loop.run_until_complete(run())
