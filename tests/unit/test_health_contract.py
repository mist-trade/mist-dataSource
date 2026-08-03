import pytest
from pydantic import ValidationError

from src.ws.health_contract import (
    BridgeHealth,
    QmtDatasourceHealth,
    TdxDatasourceHealth,
)


def bridge() -> dict[str, object]:
    return {
        "ready": True,
        "ownerId": "owner-1",
        "ownerGeneration": 1,
        "bridgeBuildId": "bridge-v2",
        "bridgeArtifactSha256": "a" * 64,
    }


@pytest.mark.parametrize(
    ("model", "payload", "retired"),
    [
        (
            TdxDatasourceHealth,
            {
                "status": "ok",
                "instance": "tdx",
                "realtimeMode": "builtin",
                "connections": 1,
                "wsConnected": True,
                "tdxHttpReachable": True,
                "lastError": None,
                "bridge": bridge(),
            },
            "tdxRealtimeBridgeReady",
        ),
        (
            QmtDatasourceHealth,
            {
                "status": "ok",
                "instance": "qmt",
                "realtimeMode": "builtin",
                "bridge": bridge(),
                "realtime": {"state": "ready"},
                "subscriptions": {"ready": True},
            },
            "collectorReady",
        ),
    ],
)
def test_root_health_models_reject_retired_top_level_fields(
    model: type[TdxDatasourceHealth] | type[QmtDatasourceHealth],
    payload: dict[str, object],
    retired: str,
) -> None:
    payload[retired] = True

    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_bridge_health_requires_normalized_owner_metadata() -> None:
    payload = bridge()
    payload["generation"] = payload.pop("ownerGeneration")

    with pytest.raises(ValidationError):
        BridgeHealth.model_validate(payload)


def test_tdx_health_requires_bridge_artifact_identity() -> None:
    payload = {
        "status": "ok",
        "instance": "tdx",
        "realtimeMode": "builtin",
        "connections": 1,
        "wsConnected": True,
        "tdxHttpReachable": True,
        "lastError": None,
        "bridge": bridge(),
    }
    del payload["bridge"]["bridgeArtifactSha256"]  # type: ignore[index]

    with pytest.raises(ValidationError):
        TdxDatasourceHealth.model_validate(payload)
