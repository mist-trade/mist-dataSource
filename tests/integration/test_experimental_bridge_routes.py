"""HTTP contract replay for the terminal bridge endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from src.datasource.tdx.experimental_gateway import ExperimentalTdxRealtimeGateway
from tdx.routes.experimental import router


class _BroadcastCapture:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


def _client() -> tuple[TestClient, _BroadcastCapture]:
    app = FastAPI()
    app.include_router(router)
    app.state.tdx_experimental_gateway = ExperimentalTdxRealtimeGateway()
    capture = _BroadcastCapture()
    app.state.tdx_experimental_ws_manager = capture
    return TestClient(app, client=("127.0.0.1", 43123)), capture


def _owner_payload(*, mode: str = "builtin_experimental") -> dict[str, Any]:
    return {
        "ownerId": "terminal-script-test",
        "mode": mode,
        "bridgeBuildId": "test-build",
        "bridgeArtifactSha256": "test-sha256",
        "acquisitionProfile": "tdx.get_market_snapshot",
        "schemaVersion": 0,
        "draftRevision": 1,
    }


def _native_snapshot() -> dict[str, Any]:
    return {
        "Code": "600519.SH",
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


def test_terminal_payloads_complete_real_http_route_chain() -> None:
    client, capture = _client()
    with client:
        owner = client.post("/tdx/bridge/owner", json=_owner_payload()).json()
        lease = owner["leaseToken"]
        epoch = owner["streamEpoch"]

        desired = client.post("/tdx/bridge/desired", json={"symbols": ["600519.SH"]}).json()
        revision = desired["desiredRevision"]

        poll = client.post(
            "/tdx/bridge/poll",
            json={
                "leaseToken": lease,
                "streamEpoch": epoch,
                "appliedRevision": -1,
            },
        )
        assert poll.status_code == 200
        assert poll.json()["subscribe"] == ["600519.SH"]

        result = client.post(
            "/tdx/bridge/result",
            json={
                "leaseToken": lease,
                "streamEpoch": epoch,
                "desiredRevision": revision,
                "appliedRevision": revision,
                "active": ["600519.SH"],
                "rejected": [],
            },
        )
        assert result.status_code == 200
        assert result.json()["converged"] is True

        snapshot = client.post(
            "/tdx/bridge/snapshot",
            json={
                "leaseToken": lease,
                "streamEpoch": epoch,
                "symbol": "600519.SH",
                "producerSequence": 1,
                "capturedAt": "2026-07-17T14:30:01.000+08:00",
                "native": _native_snapshot(),
            },
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["accepted"] is True
        assert len(capture.messages) == 1


def test_owner_mode_and_epoch_are_semantically_enforced() -> None:
    client, _ = _client()
    with client:
        wrong_mode = client.post("/tdx/bridge/owner", json=_owner_payload(mode="legacy"))
        assert wrong_mode.status_code == 200
        assert wrong_mode.json()["error"]["code"] == "TDX_BRIDGE_MODE_MISMATCH"

        owner = client.post("/tdx/bridge/owner", json=_owner_payload()).json()
        stale_epoch = client.post(
            "/tdx/bridge/poll",
            json={
                "leaseToken": owner["leaseToken"],
                "streamEpoch": "stale-epoch",
                "appliedRevision": -1,
            },
        )
        assert stale_epoch.status_code == 200
        assert stale_epoch.json()["error"]["code"] == "TDX_BRIDGE_EPOCH_MISMATCH"


def test_missing_terminal_contract_fields_fail_validation() -> None:
    client, _ = _client()
    with client:
        owner = _owner_payload()
        owner.pop("mode")
        assert client.post("/tdx/bridge/owner", json=owner).status_code == 422

        assert (
            client.post(
                "/tdx/bridge/poll",
                json={"leaseToken": "lease", "appliedRevision": -1},
            ).status_code
            == 422
        )


def test_bridge_routes_reject_unknown_fields_and_remote_health() -> None:
    client, _ = _client()
    with client:
        payload = _owner_payload()
        payload["unexpected"] = "must-not-be-ignored"
        assert client.post("/tdx/bridge/owner", json=payload).status_code == 422

    app = FastAPI()
    app.include_router(router)
    app.state.tdx_experimental_gateway = ExperimentalTdxRealtimeGateway()
    with TestClient(app, client=("203.0.113.10", 43123)) as remote:
        response = remote.get("/tdx/bridge/health")
        assert response.status_code == 403
        assert response.json()["detail"] == {
            "code": "TDX_BRIDGE_NOT_LOOPBACK",
            "message": "bridge endpoints are loopback-only",
            "retryable": False,
        }


def test_gateway_errors_preserve_retryable_classification() -> None:
    client, _ = _client()
    with client:
        owner = client.post("/tdx/bridge/owner", json=_owner_payload()).json()
        response = client.post(
            "/tdx/bridge/poll",
            json={
                "leaseToken": owner["leaseToken"],
                "streamEpoch": "stale",
                "appliedRevision": -1,
            },
        ).json()
        assert response["error"]["code"] == "TDX_BRIDGE_EPOCH_MISMATCH"
        assert response["error"]["retryable"] is False
