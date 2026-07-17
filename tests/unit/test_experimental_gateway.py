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
    def test_epoch_callback_carries_the_current_owner_generation(
        self, async_loop, monkeypatch
    ) -> None:
        events: list[tuple[str, int, str, str]] = []

        async def capture(epoch: str, generation: int, owner_id: str, build_id: str) -> None:
            events.append((epoch, generation, owner_id, build_id))

        clock = 100.0
        monkeypatch.setattr("src.datasource.tdx.experimental_gateway.time.monotonic", lambda: clock)
        callback_gateway = ExperimentalTdxRealtimeGateway(on_epoch_change=capture)
        async_loop.run_until_complete(
            callback_gateway.register_owner(
                owner_id="bridge-a",
                bridge_build_id="build-a",
                bridge_artifact_sha256="sha-a",
                **CONTRACT_KWARGS,
            )
        )
        clock = 111.0
        second = async_loop.run_until_complete(
            callback_gateway.register_owner(
                owner_id="bridge-b",
                bridge_build_id="build-b",
                bridge_artifact_sha256="sha-b",
                **CONTRACT_KWARGS,
            )
        )

        assert events[-1] == (
            second["streamEpoch"],
            second["generation"],
            "bridge-b",
            "build-b",
        )

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

    def test_fresh_owner_refuses_eviction_by_different_owner(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        """A fresh owner must NOT be evicted by a different owner."""
        async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-1",
                bridge_build_id="sha",
                bridge_artifact_sha256="9f2c",
                **CONTRACT_KWARGS,
            )
        )
        with pytest.raises(GatewayError) as exc_info:
            async_loop.run_until_complete(
                gateway.register_owner(
                    owner_id="bridge-2",
                    bridge_build_id="sha",
                    bridge_artifact_sha256="9f2c",
                    **CONTRACT_KWARGS,
                )
            )
        assert exc_info.value.code == "TDX_BRIDGE_OWNER_ACTIVE"

    def test_owner_lease_expires(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop, monkeypatch
    ) -> None:
        clock = 100.0
        monkeypatch.setattr("src.datasource.tdx.experimental_gateway.time.monotonic", lambda: clock)
        result = async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-1",
                bridge_build_id="sha",
                bridge_artifact_sha256="9f2c",
                **CONTRACT_KWARGS,
            )
        )
        clock = 111.0
        with pytest.raises(GatewayError) as exc_info:
            async_loop.run_until_complete(
                gateway.poll(
                    lease_token=result["leaseToken"],
                    stream_epoch=result["streamEpoch"],
                )
            )
        assert exc_info.value.code == "TDX_BRIDGE_NO_OWNER"
        assert exc_info.value.retryable is True


class TestSubscriptionConvergence:
    def test_transport_identities_are_exact_and_stably_deduplicated(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b",
                bridge_build_id="s",
                bridge_artifact_sha256="h",
                **CONTRACT_KWARGS,
            )
            revision = await gateway.sync_desired(["SH600519", "600519.SH", "SH600519"])
            poll = await gateway.poll(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
            )
            assert poll["desiredSymbols"] == ["SH600519", "600519.SH"]

            result = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=revision,
                applied_revision=revision,
                active=["600519.SH"],
                rejected=[],
            )
            assert result["converged"] is False

        async_loop.run_until_complete(run())

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
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
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
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=[],
                rejected=[{"symbol": "600519.SH", "reason": "denied"}],
            )
            assert res["converged"] is False
            assert res["failureCode"] == "TDX_BRIDGE_NATIVE_REJECTED"
            assert res["retryable"] is True
            assert res["retryAttempt"] == 1
            assert res["retryAfterMs"] == 250

            second = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=[],
                rejected=[{"symbol": "600519.SH", "reason": "still pending"}],
            )
            assert second["retryAttempt"] == 2
            assert second["retryAfterMs"] == 500

            health = await gateway.health()
            assert health["attemptedRevision"] == rev
            assert health["lastFailureRetryable"] is True
            assert health["reconcileRetryAttempt"] == 2

        async_loop.run_until_complete(run())

    def test_permanent_reconcile_failure_has_no_backoff(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev = await gateway.sync_desired(["600519.SH"])
            result = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=[],
                rejected=[
                    {
                        "symbol": "600519.SH",
                        "reason": "provider denied permanently",
                        "code": "TDX_BRIDGE_NATIVE_DENIED",
                        "retryable": False,
                    }
                ],
            )
            assert result["retryable"] is False
            assert result["retryAfterMs"] == 0
            assert result["failureCode"] == "TDX_BRIDGE_NATIVE_DENIED"

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
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],  # missing 000001.SZ
                rejected=[],
            )
            assert res["converged"] is False

        async_loop.run_until_complete(run())

    def test_non_convergence_clears_observed_native(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        """After a converged set, a non-converged result must clear observedNative
        so stale symbols can no longer post snapshots."""

        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            rev1 = await gateway.sync_desired(["600519.SH", "000001.SZ"])
            await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev1,
                applied_revision=rev1,
                active=["600519.SH", "000001.SZ"],
                rejected=[],
            )
            rev2 = await gateway.sync_desired(["600519.SH"])
            await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev2,
                applied_revision=rev2,
                active=["600519.SH", "000001.SZ"],
                rejected=[],
            )
            with pytest.raises((GatewayError, Exception)):
                await gateway.post_snapshot(
                    lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                    stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                    symbol="000001.SZ",
                    producer_sequence=1,
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native={**_native_snapshot(), "Code": "000001.SZ"},
                )

        async_loop.run_until_complete(run())

    def test_stale_revision_result_ignored(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        """post_result for a stale desired_revision must not converge."""

        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            await gateway.sync_desired(["600519.SH"])
            res = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=-999,
                applied_revision=-999,
                active=["600519.SH"],
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
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            r1 = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                producer_sequence=1,
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            assert r1["accepted"] is True
            assert r1["sequence"] == 1
            r2 = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
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
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                producer_sequence=7,
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            # Retry same producer_sequence=7 → must be rejected (not re-broadcast).
            with pytest.raises(GatewayError) as exc_info:
                await gateway.post_snapshot(
                    lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                    stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
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
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=rev,
                applied_revision=rev,
                active=["600519.SH"],
                rejected=[],
            )
            invalid_values = (
                "not-a-timestamp",
                "2026-07-17T14:30+08:00",
                "2026-07-17T14:30:00+08",
                "2026-02-30T14:30:00+08:00",
                "2026-07-17T25:30:00+08:00",
                " 2026-07-17T14:30:00+08:00",
            )
            for captured_at in invalid_values:
                with pytest.raises(GatewayError) as exc_info:
                    await gateway.post_snapshot(
                        lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                        stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                        symbol="600519.SH",
                        producer_sequence=1,
                        captured_at=captured_at,
                        native=_native_snapshot(),
                    )
                assert exc_info.value.code == "TDX_BRIDGE_INVALID_TIMESTAMP"

        async_loop.run_until_complete(run())

    def test_rejects_symbol_before_convergence(
        self, gateway: ExperimentalTdxRealtimeGateway, async_loop
    ) -> None:
        async def run() -> None:
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            await gateway.sync_desired(["600519.SH"])
            # Don't report convergence.
            with pytest.raises(GatewayError) as exc_info:
                await gateway.post_snapshot(
                    lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                    stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
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
                    stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                    symbol="600519.SH",
                    producer_sequence=1,
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_LEASE_INVALID"

        async_loop.run_until_complete(run())
