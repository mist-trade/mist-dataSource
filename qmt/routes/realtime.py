"""Loopback-only diagnostics for the QMT experimental realtime transport."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from src.datasource.qmt.realtime import QmtRealtimeCollector

router = APIRouter()


def _require_loopback(request: Request) -> None:
    client = request.client
    if client is None or client.host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "QMT_REALTIME_NOT_LOOPBACK",
                "message": "QMT experimental realtime diagnostics are loopback-only",
                "retryable": False,
            },
        )


@router.get("/qmt/realtime/health")
async def realtime_health(request: Request) -> dict[str, Any]:
    _require_loopback(request)
    if request.query_params:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "QMT_REALTIME_UNKNOWN_FIELDS",
                "message": "QMT realtime health accepts no query fields",
                "retryable": False,
                "fields": sorted(request.query_params.keys()),
            },
        )
    collector: QmtRealtimeCollector | None = getattr(
        request.app.state, "qmt_realtime_collector", None
    )
    if collector is None:
        raise HTTPException(status_code=404, detail="QMT experimental realtime is disabled")
    return collector.health()
