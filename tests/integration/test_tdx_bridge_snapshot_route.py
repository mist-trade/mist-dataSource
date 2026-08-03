import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.datasource.tdx.realtime.gateway import (
    ACCEPTED_ACQUISITION_PROFILE,
    ACCEPTED_SCHEMA_VERSION,
    TdxRealtimeGateway,
)
from src.ws.manager import ConnectionManager
from tdx.routes.bridge import router


@pytest.mark.asyncio
async def test_tdx_snapshot_route_has_no_producer_sequence_or_item_ack() -> None:
    app = FastAPI()
    app.include_router(router)
    gateway = TdxRealtimeGateway()
    app.state.tdx_realtime_gateway = gateway
    app.state.tdx_realtime_ws_manager = ConnectionManager()
    owner = await gateway.register_owner(
        owner_id="tdx-test",
        bridge_build_id="test",
        bridge_artifact_sha256="sha",
        acquisition_profile=ACCEPTED_ACQUISITION_PROFILE,
        schema_version=ACCEPTED_SCHEMA_VERSION,
    )
    revision = await gateway.sync_desired(["600519.SH"])
    await gateway.post_result(
        lease_token=owner["leaseToken"],
        stream_epoch=owner["streamEpoch"],
        desired_revision=revision,
        applied_revision=revision,
        active=["600519.SH"],
        rejected=[],
    )
    body = {
        "leaseToken": owner["leaseToken"],
        "streamEpoch": owner["streamEpoch"],
        "symbol": "600519.SH",
        "capturedAt": "2026-07-26T10:00:00+08:00",
        "native": {
            "Code": "600519.SH",
            "ErrorId": 0,
            "Now": 1685.0,
            "Open": 1670.0,
            "Max": 1690.0,
            "Min": 1665.0,
            "LastClose": 1672.5,
            "Volume": "12345600",
            "Amount": "20800000000",
        },
    }
    transport = ASGITransport(app=app, client=("127.0.0.1", 12345))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/tdx/bridge/snapshot", json=body)
        assert response.status_code == 200
        assert response.json() == {}

        invalid = await client.post(
            "/tdx/bridge/snapshot",
            json={**body, "producerSequence": 1},
        )
        assert invalid.status_code == 422
