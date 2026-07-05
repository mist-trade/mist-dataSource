"""Integration tests for the native QMT datasource surface."""

import struct
from datetime import datetime
from pathlib import Path

import pytest

import qmt.main
from src.datasource.contracts import BEIJING_TZ
from src.datasource.qmt.local_dat import QmtLocalDatReader
from src.datasource.qmt_provider import QmtDatasourceProvider


def _timestamp(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=BEIJING_TZ).timestamp())


def _write_daily_dat(root: Path, symbol: str) -> None:
    code, market = symbol.split(".")
    path = root / market / "86400" / f"{code}.DAT"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"QMTDAT00")
        handle.write(struct.pack("<IIIIIIII", _timestamp(2026, 7, 1), 10000, 11000, 9900, 10500, 0, 123, 1))
        handle.write(struct.pack("<IIIIIIII", 0, 0, 0, 0, 0, 0, 0, 0))


@pytest.fixture
def qmt_dat_provider(tmp_path: Path):
    _write_daily_dat(tmp_path, "000001.SZ")
    previous = getattr(qmt.main.app.state, "qmt_provider", None)
    qmt.main.app.state.qmt_provider = QmtDatasourceProvider(
        local_dat_reader=QmtLocalDatReader(
            data_dir=tmp_path,
            enabled=True,
            now=lambda: datetime(2026, 7, 5, 17, 0, tzinfo=BEIJING_TZ),
            stability_wait_ms=0,
        )
    )
    try:
        yield
    finally:
        qmt.main.app.state.qmt_provider = previous


@pytest.mark.asyncio
@pytest.mark.usefixtures("qmt_dat_provider")
async def test_qmt_v1_bars_query_returns_native_market_data(qmt_client) -> None:
    response = await qmt_client.post(
        "/v1/bars/query",
        json={
            "fields": ["close", "volume"],
            "stock_list": ["000001.SZ"],
            "period": "1d",
            "start_time": "",
            "end_time": "",
            "count": 1,
            "dividend_type": "none",
            "fill_data": True,
            "include_raw": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["provider"] == "qmt"
    assert body["data"] == {
        "marketData": {
            "000001.SZ": {
                "close": {"20260701": 10.5},
                "volume": {"20260701": 123.0},
            }
        },
        "source": "local_dat",
    }


@pytest.mark.asyncio
@pytest.mark.usefixtures("qmt_dat_provider")
async def test_qmt_v1_bars_query_rejects_tdx_style_fields(qmt_client) -> None:
    response = await qmt_client.post(
        "/v1/bars/query",
        json={
            "symbols": ["000001.SZ"],
            "period": "1d",
            "startTime": "",
            "endTime": "",
            "dividendType": "none",
            "fillData": True,
        },
    )

    assert response.status_code == 422


def test_qmt_route_table_contains_only_native_v1_health_and_http_bridge() -> None:
    paths = set(qmt.main.app.openapi()["paths"])

    assert "/health" in paths
    assert "/v1/bars/query" in paths
    assert {"/qmt/bridge/owner", "/qmt/bridge/poll", "/qmt/bridge/result", "/qmt/bridge/health"} <= paths
    assert not any(path.startswith("/api/qmt/") for path in paths)
    assert "/ws/quote/{client_id}" not in paths
    assert "/qmt/bridge/ws" not in paths
