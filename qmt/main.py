"""QMT datasource FastAPI application entrypoint (Port 9002).

启动方式: uvicorn qmt.main:app --port 9002 --reload
生产 QMT 接入通过大 QMT 内置 Python HTTP polling bridge 和 native `/v1` API。
"""

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from qmt.routes.bridge import router as bridge_router
from qmt.routes.v1 import router as v1_router
from qmt.routes.ws import router as ws_router
from src.core.config import settings
from src.core.logging import setup_logging
from src.datasource.qmt.command_gateway import QmtCommandGateway
from src.datasource.qmt.realtime import QmtRealtimeCollector
from src.datasource.qmt_provider import QmtDatasourceProvider
from src.ws.manager import ConnectionManager
from src.ws.protocol import ws_error, ws_quote

setup_logging()

qmt_command_gateway = QmtCommandGateway()
qmt_provider: QmtDatasourceProvider | None = QmtDatasourceProvider()
ws_manager = ConnectionManager()


async def _publish_quote(data: dict[str, Any]) -> None:
    await ws_manager.broadcast(ws_quote("qmt", data))


async def _publish_realtime_error(code: str, message: str) -> None:
    await ws_manager.broadcast(
        ws_error(
            provider="qmt",
            code=code,
            message=message,
            retryable=True,
            details={},
        )
    )


qmt_realtime_collector = QmtRealtimeCollector(
    gateway=qmt_command_gateway,
    publisher=_publish_quote,
    error_publisher=_publish_realtime_error,
)


def _sync_app_state(target_app: FastAPI) -> None:
    target_app.state.qmt_command_gateway = qmt_command_gateway
    target_app.state.qmt_provider = qmt_provider
    target_app.state.ws_manager = ws_manager
    target_app.state.qmt_realtime_collector = qmt_realtime_collector


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期管理器.

    QMT datasource 不再初始化旧 adapter。大 QMT 内置脚本通过
    HTTP polling bridge 连接，历史 bars 通过 native local-DAT provider 读取。

    Args:
        _app: FastAPI 应用实例

    Yields:
        None
    """
    _sync_app_state(_app)
    await qmt_realtime_collector.start()
    try:
        yield
    finally:
        await qmt_realtime_collector.stop()
        _sync_app_state(_app)


app = FastAPI(
    title="Mist DataSource - QMT",
    description="QMT 数据源 - native bars / full-QMT HTTP polling bridge",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    """健康检查端点."""
    reader = qmt_provider.local_dat_reader if qmt_provider else None
    return {
        "status": "ok",
        "instance": "qmt",
        "bridge": qmt_command_gateway.health(),
        "localDat": {
            "enabled": bool(reader and reader.enabled),
            "dataDirConfigured": bool(reader and str(reader.data_dir)),
        },
        "realtime": qmt_realtime_collector.health(),
    }


_sync_app_state(app)
app.include_router(v1_router, tags=["V1"])
app.include_router(bridge_router, prefix="/qmt/bridge", tags=["QMT Bridge"])
app.include_router(ws_router, prefix="/ws", tags=["WebSocket"])
