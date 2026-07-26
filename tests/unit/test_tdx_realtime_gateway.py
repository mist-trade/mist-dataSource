"""Unit tests for the formal TDX realtime gateway state machine."""

from __future__ import annotations

import asyncio

import pytest

from src.datasource.tdx.realtime.runtime import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_SCHEMA_VERSION,
    GatewayError,
    TdxRealtimeGateway,
)

CONTRACT_KWARGS = {
    "acquisition_profile": ACCEPTED_ACQUISITION_PROFILE,
    "schema_version": ACCEPTED_SCHEMA_VERSION,
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
def gateway() -> TdxRealtimeGateway:
    return TdxRealtimeGateway(max_subscriptions=100)


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
        monkeypatch.setattr("src.datasource.tdx.realtime.runtime.time.monotonic", lambda: clock)
        callback_gateway = TdxRealtimeGateway(on_epoch_change=capture)
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
        self, gateway: TdxRealtimeGateway, async_loop
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
        assert result["acceptedContractTuple"]["payloadType"] == "mist.realtime.native_snapshot"

    def test_contract_mismatch_rejected(
        self, gateway: TdxRealtimeGateway, async_loop
    ) -> None:
        with pytest.raises(GatewayError) as exc_info:
            async_loop.run_until_complete(
                gateway.register_owner(
                    owner_id="bridge-1",
                    bridge_build_id="sha",
                    bridge_artifact_sha256="9f2c",
                    acquisition_profile="wrong",
                    schema_version=0,
                )
            )
        assert exc_info.value.code == "TDX_BRIDGE_CONTRACT_MISMATCH"

    def test_new_generation_creates_new_epoch(
        self, gateway: TdxRealtimeGateway, async_loop
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
        self, gateway: TdxRealtimeGateway, async_loop
    ) -> None:
        """A single registration attempt cannot evict a fresh owner."""
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
        assert exc_info.value.retry_after_ms == 1_000

    def test_continuous_new_owner_replaces_fresh_owner_after_grace(
        self, gateway: TdxRealtimeGateway, async_loop, monkeypatch
    ) -> None:
        clock = 100.0
        monkeypatch.setattr("src.datasource.tdx.realtime.runtime.time.monotonic", lambda: clock)
        old = async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-old",
                bridge_build_id="sha-old",
                bridge_artifact_sha256="artifact-old",
                **CONTRACT_KWARGS,
            )
        )

        for second in range(5):
            clock = 100.0 + second
            with pytest.raises(GatewayError) as exc_info:
                async_loop.run_until_complete(
                    gateway.register_owner(
                        owner_id="bridge-new",
                        bridge_build_id="sha-new",
                        bridge_artifact_sha256="artifact-new",
                        **CONTRACT_KWARGS,
                    )
                )
            assert exc_info.value.code == "TDX_BRIDGE_OWNER_ACTIVE"

        # Prove the old process is still heartbeating and fresh immediately
        # before the bounded takeover.
        clock = 104.5
        async_loop.run_until_complete(
            gateway.poll(
                lease_token=old["leaseToken"],
                stream_epoch=old["streamEpoch"],
            )
        )
        clock = 105.0
        new = async_loop.run_until_complete(
            gateway.register_owner(
                owner_id="bridge-new",
                bridge_build_id="sha-new",
                bridge_artifact_sha256="artifact-new",
                **CONTRACT_KWARGS,
            )
        )
        assert gateway.owner is not None
        assert gateway.owner.owner_id == "bridge-new"

        with pytest.raises(GatewayError) as exc_info:
            async_loop.run_until_complete(
                gateway.poll(
                    lease_token=old["leaseToken"],
                    stream_epoch=old["streamEpoch"],
                )
            )
        assert exc_info.value.code == "TDX_BRIDGE_LEASE_INVALID"

        with pytest.raises(GatewayError) as exc_info:
            async_loop.run_until_complete(
                gateway.register_owner(
                    owner_id="bridge-old",
                    bridge_build_id="sha-old",
                    bridge_artifact_sha256="artifact-old",
                    **CONTRACT_KWARGS,
                )
            )
        assert exc_info.value.code == "TDX_BRIDGE_OWNER_RETIRED"
        assert gateway.owner.lease_token == new["leaseToken"]

    def test_owner_lease_expires(
        self, gateway: TdxRealtimeGateway, async_loop, monkeypatch
    ) -> None:
        clock = 100.0
        monkeypatch.setattr("src.datasource.tdx.realtime.runtime.time.monotonic", lambda: clock)
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
        self, gateway: TdxRealtimeGateway, async_loop
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
            assert poll["desiredSymbols"] == ["600519.SH"]

            result = await gateway.post_result(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                desired_revision=revision,
                applied_revision=revision,
                active=["600519.SH"],
                rejected=[],
            )
            assert result["converged"] is True

        async_loop.run_until_complete(run())

    def test_converged_after_clean_reconcile(
        self, gateway: TdxRealtimeGateway, async_loop
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
        self, gateway: TdxRealtimeGateway, async_loop
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
        self, gateway: TdxRealtimeGateway, async_loop
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
        self, gateway: TdxRealtimeGateway, async_loop
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
        self, gateway: TdxRealtimeGateway, async_loop
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
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native={**_native_snapshot(), "Code": "000001.SZ"},
                )

        async_loop.run_until_complete(run())

    def test_stale_revision_result_ignored(
        self, gateway: TdxRealtimeGateway, async_loop
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
    def test_accepts_converged_symbol_as_schema_v2_map(
        self, gateway: TdxRealtimeGateway, async_loop
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
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            assert r1["accepted"] is True
            assert r1["frame"] == {
                "schemaVersion": 2,
                "capturedAt": "2026-07-16T14:30:01.000+08:00",
                "native": {"600519.SH": _native_snapshot()},
            }
            health = await gateway.health()
            assert health["lastSnapshotAt"] is not None
            assert health["lastSnapshotAgeSeconds"] >= 0
            r2 = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                captured_at="2026-07-16T14:30:02.000+08:00",
                native=_native_snapshot(),
            )
            assert r2["accepted"] is True
            assert "sequence" not in r2["frame"]

        async_loop.run_until_complete(run())

    def test_repeated_latest_state_has_no_producer_dedup_contract(
        self, gateway: TdxRealtimeGateway, async_loop
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
            first = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            second = await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            assert first["accepted"] is True
            assert second["accepted"] is True

        async_loop.run_until_complete(run())

    def test_native_evidence_is_copied_and_cleared_on_desired_change(
        self, gateway: TdxRealtimeGateway, async_loop
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
            await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )

            evidence = await gateway.read_native_evidence("600519.SH")
            assert evidence["native"]["Now"] == "1685.0"
            assert "leaseToken" not in evidence
            evidence["native"]["Now"] = "mutated"
            assert (await gateway.read_native_evidence("600519.SH"))["native"]["Now"] == "1685.0"

            await gateway.sync_desired([])
            with pytest.raises(GatewayError) as exc_info:
                await gateway.read_native_evidence("600519.SH")
            assert exc_info.value.code == "TDX_BRIDGE_EVIDENCE_NOT_FOUND"

        async_loop.run_until_complete(run())

    def test_native_evidence_is_cleared_on_owner_epoch_change(
        self, gateway: TdxRealtimeGateway, async_loop
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
            await gateway.post_snapshot(
                lease_token=gateway.owner.lease_token,  # type: ignore[union-attr]
                stream_epoch=gateway.owner.stream_epoch,  # type: ignore[union-attr]
                symbol="600519.SH",
                captured_at="2026-07-16T14:30:01.000+08:00",
                native=_native_snapshot(),
            )
            await gateway.register_owner(
                owner_id="b", bridge_build_id="s", bridge_artifact_sha256="h", **CONTRACT_KWARGS
            )
            with pytest.raises(GatewayError) as exc_info:
                await gateway.read_native_evidence("600519.SH")
            assert exc_info.value.code == "TDX_BRIDGE_EVIDENCE_NOT_FOUND"

        async_loop.run_until_complete(run())

    def test_rejects_non_rfc3339_captured_at(
        self, gateway: TdxRealtimeGateway, async_loop
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
                        captured_at=captured_at,
                        native=_native_snapshot(),
                    )
                assert exc_info.value.code == "TDX_BRIDGE_INVALID_TIMESTAMP"

        async_loop.run_until_complete(run())

    def test_rejects_symbol_before_convergence(
        self, gateway: TdxRealtimeGateway, async_loop
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
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_SYMBOL_NOT_CONVERGED"

        async_loop.run_until_complete(run())

    def test_invalid_lease_rejected(
        self, gateway: TdxRealtimeGateway, async_loop
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
                    captured_at="2026-07-16T14:30:01.000+08:00",
                    native=_native_snapshot(),
                )
            assert exc_info.value.code == "TDX_BRIDGE_LEASE_INVALID"

        async_loop.run_until_complete(run())
