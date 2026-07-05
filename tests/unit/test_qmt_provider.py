import struct
from datetime import datetime
from pathlib import Path

import pytest

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
        for record in (
            (_timestamp(2026, 7, 1), 10000, 11000, 9900, 10500, 123),
            (0, 0, 0, 0, 0, 0),
        ):
            ts, open_p, high_p, low_p, close_p, volume_lots = record
            handle.write(struct.pack("<IIIIIIII", ts, open_p, high_p, low_p, close_p, 0, volume_lots, 1))


@pytest.mark.asyncio
async def test_qmt_provider_get_bars_returns_native_market_data(tmp_path: Path) -> None:
    _write_daily_dat(tmp_path, "000001.SZ")
    reader = QmtLocalDatReader(
        data_dir=tmp_path,
        enabled=True,
        now=lambda: datetime(2026, 7, 5, 17, 0, tzinfo=BEIJING_TZ),
        stability_wait_ms=0,
    )
    provider = QmtDatasourceProvider(local_dat_reader=reader)

    result = await provider.get_bars(
        stock_list=["000001.SZ"],
        period="1d",
        start_time=None,
        end_time=None,
        count=1,
        fields=["close", "volume"],
        dividend_type="none",
        fill_data=True,
        include_raw=False,
    )

    assert result["source"] == "local_dat"
    assert result["marketData"] == {
        "000001.SZ": {
            "close": {"20260701": 10.5},
            "volume": {"20260701": 123.0},
        }
    }
