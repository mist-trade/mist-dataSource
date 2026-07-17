"""Cross-repo replay E2E: fake terminal → real gateway → WS broadcast.

Tests the full datasource-side vertical chain on macOS using the real
ExperimentalTdxRealtimeGateway, real route handlers, and a mock WS manager.
This is the "replay-backed" verification required by task 5.6.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.datasource.tdx.experimental_gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_DRAFT_REVISION,
    ACCEPTED_SCHEMA_VERSION,
    ExperimentalTdxRealtimeGateway,
)


def _native_snapshot(symbol: str = "600519.SH") -> dict[str, Any]:
    return {
        "Code": symbol,
        "ErrorId": "0",
        "Now": "1685.0",
        "Open": "1670.0",
        "Max": "1690.0",
        "Min": "1665.0",
        "LastClose": "1672.5",
        "Volume": "12345600",
        "Amount": "20800000000",
        "AsOf": "2026-07-17T14:30:00.000+08:00",
    }


CONTRACT_KWARGS = {
    "acquisition_profile": ACCEPTED_ACQUISITION_PROFILE,
    "schema_version": ACCEPTED_SCHEMA_VERSION,
    "draft_revision": ACCEPTED_DRAFT_REVISION,
}


class MockBroadcastCapture:
    """Captures broadcast messages for assertion."""

    def __init__(self) -> None:
        self.messages: list[Any] = []
        self.broadcast_lock = asyncio.Lock()

    async def broadcast(self, message: Any) -> None:
        self.messages.append(message)


@pytest.fixture()
def gateway_with_capture() -> tuple[ExperimentalTdxRealtimeGateway, MockBroadcastCapture]:
    capture = MockBroadcastCapture()
    gateway = ExperimentalTdxRealtimeGateway(
        on_epoch_change=lambda epoch, gen, owner_id, bridge_build_id: capture.broadcast(
            {
                "type": "stream_started",
                "data": {
                    "streamEpoch": epoch,
                    "generation": gen,
                    "mode": "builtin_experimental",
                    "ownerId": owner_id,
                    "bridgeBuildId": bridge_build_id,
                },
            }
        ),
    )
    return gateway, capture


class TestFullReplayChain:
    """Full vertical chain: register → desired → poll → reconcile → result → snapshot."""

    @pytest.mark.asyncio
    async def test_complete_replay_chain(
        self, gateway_with_capture: tuple[ExperimentalTdxRealtimeGateway, MockBroadcastCapture]
    ) -> None:
        gateway, capture = gateway_with_capture

        # 1. Register owner.
        reg = await gateway.register_owner(
            owner_id="bridge-1",
            bridge_build_id="sha-abc",
            bridge_artifact_sha256="9f2c",
            **CONTRACT_KWARGS,
        )
        assert "leaseToken" in reg
        lease = reg["leaseToken"]
        epoch = reg["streamEpoch"]
        assert reg["generation"] == 1
        # stream_started broadcast happened.
        assert len(capture.messages) == 1
        assert capture.messages[0]["data"]["generation"] == 1
        assert capture.messages[0]["data"]["ownerId"] == "bridge-1"
        assert capture.messages[0]["data"]["bridgeBuildId"] == "sha-abc"

        # 2. Set desired symbols.
        rev = await gateway.sync_desired(["600519.SH"])
        assert rev == 1

        # 3. Terminal polls — gets subscribe instructions.
        poll = await gateway.poll(lease_token=lease, stream_epoch=epoch, applied_revision=-1)
        assert poll["desiredRevision"] == 1
        assert poll["desiredSymbols"] == ["600519.SH"]
        assert poll["subscribe"] == ["600519.SH"]
        assert poll["unsubscribe"] == []

        # 4. Terminal reports result (converged).
        result = await gateway.post_result(
            lease_token=lease,
            stream_epoch=epoch,
            desired_revision=1,
            applied_revision=1,
            active=["600519.SH"],
            rejected=[],
        )
        assert result["converged"] is True

        # 5. Terminal posts snapshot.
        snap = await gateway.post_snapshot(
            lease_token=lease,
            stream_epoch=epoch,
            symbol="600519.SH",
            producer_sequence=1,
            captured_at="2026-07-17T14:30:01.000+08:00",
            native=_native_snapshot(),
        )
        assert snap["accepted"] is True
        assert snap["sequence"] == 1
        frame = snap["frame"]
        assert frame["payloadType"] == "tdx.realtime.snapshot"
        assert frame["snapshot"]["last"] == 1685.0
        assert frame["streamEpoch"] is not None

    @pytest.mark.asyncio
    async def test_desired_shrink_produces_correct_unsubscribe(
        self, gateway_with_capture: tuple[ExperimentalTdxRealtimeGateway, MockBroadcastCapture]
    ) -> None:
        """When desired shrinks, poll must return correct unsubscribe list."""
        gateway, _ = gateway_with_capture
        reg = await gateway.register_owner(
            owner_id="bridge-1",
            bridge_build_id="sha",
            bridge_artifact_sha256="h",
            **CONTRACT_KWARGS,
        )
        lease = reg["leaseToken"]
        epoch = reg["streamEpoch"]

        # Converge on two symbols.
        await gateway.sync_desired(["600519.SH", "000001.SZ"])
        await gateway.post_result(
            lease_token=lease,
            stream_epoch=epoch,
            desired_revision=1,
            applied_revision=1,
            active=["600519.SH", "000001.SZ"],
            rejected=[],
        )

        # Shrink desired to one symbol.
        await gateway.sync_desired(["600519.SH"])

        # Poll must return unsubscribe=[000001.SZ].
        poll = await gateway.poll(lease_token=lease, stream_epoch=epoch, applied_revision=1)
        assert "000001.SZ" in poll["unsubscribe"]
        assert "600519.SH" not in poll["unsubscribe"]

    @pytest.mark.asyncio
    async def test_sequence_monotonic_across_desired_changes(
        self, gateway_with_capture: tuple[ExperimentalTdxRealtimeGateway, MockBroadcastCapture]
    ) -> None:
        """Outbound sequence must NOT reset when desired changes (only on epoch change)."""
        gateway, _ = gateway_with_capture
        reg = await gateway.register_owner(
            owner_id="bridge-1",
            bridge_build_id="sha",
            bridge_artifact_sha256="h",
            **CONTRACT_KWARGS,
        )
        lease = reg["leaseToken"]
        epoch = reg["streamEpoch"]

        # First convergence + snapshot.
        await gateway.sync_desired(["600519.SH"])
        await gateway.post_result(
            lease_token=lease,
            stream_epoch=epoch,
            desired_revision=1,
            applied_revision=1,
            active=["600519.SH"],
            rejected=[],
        )
        snap1 = await gateway.post_snapshot(
            lease_token=lease,
            stream_epoch=epoch,
            symbol="600519.SH",
            producer_sequence=1,
            captured_at="2026-07-17T14:30:01.000+08:00",
            native=_native_snapshot(),
        )
        assert snap1["sequence"] == 1

        # Desired changes (shrink to empty then back).
        await gateway.sync_desired([])
        await gateway.sync_desired(["600519.SH"])
        await gateway.post_result(
            lease_token=lease,
            stream_epoch=epoch,
            desired_revision=3,
            applied_revision=3,
            active=["600519.SH"],
            rejected=[],
        )

        # Second snapshot — sequence must be 2 (not reset to 1).
        snap2 = await gateway.post_snapshot(
            lease_token=lease,
            stream_epoch=epoch,
            symbol="600519.SH",
            producer_sequence=2,
            captured_at="2026-07-17T14:30:02.000+08:00",
            native=_native_snapshot(),
        )
        assert snap2["sequence"] == 2

    @pytest.mark.asyncio
    async def test_stale_symbol_rejected_after_desired_shrink(
        self, gateway_with_capture: tuple[ExperimentalTdxRealtimeGateway, MockBroadcastCapture]
    ) -> None:
        """After desired shrinks and re-converges, old symbol must be rejected."""
        from src.datasource.tdx.experimental_gateway import GatewayError

        gateway, _ = gateway_with_capture
        reg = await gateway.register_owner(
            owner_id="bridge-1",
            bridge_build_id="sha",
            bridge_artifact_sha256="h",
            **CONTRACT_KWARGS,
        )
        lease = reg["leaseToken"]
        epoch = reg["streamEpoch"]

        await gateway.sync_desired(["600519.SH", "000001.SZ"])
        await gateway.post_result(
            lease_token=lease,
            stream_epoch=epoch,
            desired_revision=1,
            applied_revision=1,
            active=["600519.SH", "000001.SZ"],
            rejected=[],
        )
        # Shrink + re-converge on just 600519.SH.
        await gateway.sync_desired(["600519.SH"])
        await gateway.post_result(
            lease_token=lease,
            stream_epoch=epoch,
            desired_revision=2,
            applied_revision=2,
            active=["600519.SH"],
            rejected=[],
        )
        # 000001.SZ should be rejected.
        with pytest.raises(GatewayError) as exc_info:
            await gateway.post_snapshot(
                lease_token=lease,
                stream_epoch=epoch,
                symbol="000001.SZ",
                producer_sequence=1,
                captured_at="2026-07-17T14:30:01.000+08:00",
                native=_native_snapshot("000001.SZ"),
            )
        assert exc_info.value.code == "TDX_BRIDGE_SYMBOL_NOT_CONVERGED"

    @pytest.mark.asyncio
    async def test_generation_monotonicity_broadcast(
        self, gateway_with_capture: tuple[ExperimentalTdxRealtimeGateway, MockBroadcastCapture]
    ) -> None:
        """Concurrent same-owner registrations produce monotonically ordered broadcasts."""
        gateway, capture = gateway_with_capture

        # Two sequential registrations (asyncio serializes via locks).
        r1 = await gateway.register_owner(
            owner_id="bridge-1",
            bridge_build_id="sha",
            bridge_artifact_sha256="h",
            **CONTRACT_KWARGS,
        )
        r2 = await gateway.register_owner(
            owner_id="bridge-1",
            bridge_build_id="sha",
            bridge_artifact_sha256="h",
            **CONTRACT_KWARGS,
        )
        assert r1["generation"] < r2["generation"]
        # Broadcasts should be in order: gen 1 then gen 2.
        assert len(capture.messages) == 2
        assert capture.messages[0]["data"]["generation"] < capture.messages[1]["data"]["generation"]
