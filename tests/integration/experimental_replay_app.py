"""Process-level FastAPI harness for the cross-repository replay test.

This module is only launched by the Mist Jest E2E. It uses the production
gateway, HTTP routes, WebSocket route, protocol messages, and connection
manager. The one test-only endpoint injects malformed typed frames so the
consumer's negative fences can be exercised through a real WebSocket.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel

from src.datasource.tdx.experimental_gateway import ExperimentalTdxRealtimeGateway
from src.ws.manager import ConnectionManager
from src.ws.protocol import WSMessage, ws_stream_started
from tdx.routes.experimental import router as bridge_router
from tdx.routes.experimental_ws import router as ws_router

app = FastAPI()
manager = ConnectionManager()


async def _broadcast_epoch_change(
    stream_epoch: str,
    generation: int,
    owner_id: str,
    bridge_build_id: str,
) -> None:
    await manager.broadcast(
        ws_stream_started(
            "tdx",
            {
                "streamEpoch": stream_epoch,
                "generation": generation,
                "mode": "builtin_experimental",
                "ownerId": owner_id,
                "bridgeBuildId": bridge_build_id,
            },
        )
    )


gateway = ExperimentalTdxRealtimeGateway(on_epoch_change=_broadcast_epoch_change)
app.state.tdx_experimental_gateway = gateway
app.state.tdx_experimental_ws_manager = manager
app.include_router(bridge_router)
app.include_router(ws_router)


@app.get("/__test__/health")
async def replay_health() -> dict[str, bool]:
    return {"ready": True}


class ReplayBroadcast(BaseModel):
    type: Literal["tdx.experimental.snapshot", "stream_started"]
    data: dict[str, Any]


@app.post("/__test__/broadcast")
async def replay_broadcast(body: ReplayBroadcast) -> dict[str, int]:
    await manager.broadcast(WSMessage(type=body.type, provider="tdx", data=body.data))
    return {"connections": manager.connection_count}
