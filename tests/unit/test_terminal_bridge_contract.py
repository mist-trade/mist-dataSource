"""Contract checks for payload fields produced by the terminal artifact."""

from __future__ import annotations

import pytest

from tdx.builtin_bridge.mist_tdx_realtime_bridge import BridgeOwner
from tdx.routes.realtime_bridge import OwnerRegisterRequest, PollRequest


def test_terminal_owner_registration_matches_route_model() -> None:
    owner = BridgeOwner()
    request = OwnerRegisterRequest.model_validate(owner.registration_payload())
    assert request.mode == "builtin"


def test_terminal_generation_identity_matches_route_model() -> None:
    owner = BridgeOwner()
    with pytest.raises(RuntimeError):
        owner.request_identity()

    owner.lease_token = "lease-test"
    owner.stream_epoch = "epoch-test"
    identity = owner.request_identity()
    request = PollRequest.model_validate({**identity, "appliedRevision": -1})
    assert request.leaseToken == "lease-test"
    assert request.streamEpoch == "epoch-test"
