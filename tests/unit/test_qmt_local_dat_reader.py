import struct
from datetime import datetime
from pathlib import Path

import pytest

from src.datasource.contracts import BEIJING_TZ
from src.datasource.qmt.local_dat import QmtLocalDatError, QmtLocalDatReader


def _timestamp(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> int:
    return int(datetime(year, month, day, hour, minute, tzinfo=BEIJING_TZ).timestamp())


def _write_daily_dat(root: Path, symbol: str, records: list[tuple[int, int, int, int, int, int]]) -> None:
    code, market = symbol.split(".")
    path = root / market / "86400" / f"{code}.DAT"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"QMTDAT00")
        for ts, open_p, high_p, low_p, close_p, volume_lots in records:
            handle.write(
                struct.pack(
                    "<IIIIIIII",
                    ts,
                    open_p,
                    high_p,
                    low_p,
                    close_p,
                    0,
                    volume_lots,
                    1,
                )
            )


def _write_minute_dat(root: Path, symbol: str, period_code: str, records: list[tuple[int, int, int, int, int, float, float]]) -> None:
    code, market = symbol.split(".")
    path = root / market / period_code / f"{code}.DAT"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        for ts_ms, open_p, high_p, low_p, close_p, volume, amount in records:
            handle.write(
                struct.pack(
                    "<QIIIIdd",
                    ts_ms,
                    open_p,
                    high_p,
                    low_p,
                    close_p,
                    volume,
                    amount,
                )
            )


def test_daily_dat_reads_even_records_and_normalizes_bars(tmp_path: Path) -> None:
    _write_daily_dat(
        tmp_path,
        "000001.SZ",
        [
            (_timestamp(2026, 7, 1), 10000, 11000, 9900, 10500, 123),
            (0, 0, 0, 0, 0, 0),
            (_timestamp(2026, 7, 2), 10500, 12000, 10400, 11800, 456),
            (0, 0, 0, 0, 0, 0),
        ],
    )
    reader = QmtLocalDatReader(
        data_dir=tmp_path,
        enabled=True,
        now=lambda: datetime(2026, 7, 5, 17, 0, tzinfo=BEIJING_TZ),
        stability_wait_ms=0,
    )

    bars = reader.read_bars(["000001.SZ"], period="1d", start_time=None, end_time=None, count=1)

    assert len(bars) == 1
    bar = bars[0]
    assert bar.symbol == "000001.SZ"
    assert bar.period == "1d"
    assert bar.barTime == "2026-07-02T00:00:00+08:00"
    assert bar.open == 10.5
    assert bar.high == 12.0
    assert bar.low == 10.4
    assert bar.close == 11.8
    assert bar.volume == 45600
    assert bar.amount == 0
    assert bar.provider == "qmt"


def test_minute_dat_detects_supported_record_format(tmp_path: Path) -> None:
    _write_minute_dat(
        tmp_path,
        "000001.SZ",
        "60",
        [
            (_timestamp(2026, 7, 1, 9, 31) * 1000, 102900, 103500, 102800, 103000, 1200.0, 12345.6),
            (_timestamp(2026, 7, 1, 9, 32) * 1000, 103000, 104000, 102900, 103800, 1300.0, 23456.7),
        ],
    )
    reader = QmtLocalDatReader(
        data_dir=tmp_path,
        enabled=True,
        now=lambda: datetime(2026, 7, 5, 17, 0, tzinfo=BEIJING_TZ),
        stability_wait_ms=0,
    )

    bars = reader.read_bars(
        ["000001.SZ"],
        period="1m",
        start_time="2026-07-01T09:31:00+08:00",
        end_time="2026-07-01T09:32:00+08:00",
        count=None,
    )

    assert [bar.barTime for bar in bars] == [
        "2026-07-01T09:31:00+08:00",
        "2026-07-01T09:32:00+08:00",
    ]
    assert bars[0].open == 10.29
    assert bars[1].close == 10.38
    assert bars[0].volume == 1200.0
    assert bars[0].amount == 12345.6
    assert all(bar.provider == "qmt" for bar in bars)


def test_five_minute_dat_uses_300_period_directory(tmp_path: Path) -> None:
    _write_minute_dat(
        tmp_path,
        "000001.SZ",
        "300",
        [
            (_timestamp(2026, 7, 1, 9, 35) * 1000, 103000, 104000, 102900, 103800, 1300.0, 23456.7),
        ],
    )
    reader = QmtLocalDatReader(
        data_dir=tmp_path,
        enabled=True,
        now=lambda: datetime(2026, 7, 5, 17, 0, tzinfo=BEIJING_TZ),
        stability_wait_ms=0,
    )

    bars = reader.read_bars(["000001.SZ"], period="5m", start_time=None, end_time=None, count=1)

    assert len(bars) == 1
    assert bars[0].period == "5m"
    assert bars[0].barTime == "2026-07-01T09:35:00+08:00"
    assert bars[0].close == 10.38


def test_dat_read_after_block_time_returns_retryable_error(tmp_path: Path) -> None:
    reader = QmtLocalDatReader(
        data_dir=tmp_path,
        enabled=True,
        now=lambda: datetime(2026, 7, 5, 18, 1, tzinfo=BEIJING_TZ),
        on_block="retryable_error",
        stability_wait_ms=0,
    )

    with pytest.raises(QmtLocalDatError) as exc_info:
        reader.read_bars(["000001.SZ"], period="1d", start_time=None, end_time=None, count=1)

    assert exc_info.value.code == "QMT_LOCAL_DAT_BLOCKED"
    assert exc_info.value.retryable is True
    assert exc_info.value.details["blockAfter"] == "18:00"
