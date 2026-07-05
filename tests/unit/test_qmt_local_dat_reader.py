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


def test_daily_dat_reads_even_records_as_qmt_market_data(tmp_path: Path) -> None:
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

    result = reader.read_market_data(
        ["000001.SZ"],
        period="1d",
        start_time=None,
        end_time=None,
        count=1,
        fields=[],
        include_raw=False,
    )

    market_data = result["marketData"]["000001.SZ"]
    assert market_data["open"] == {"20260702": 10.5}
    assert market_data["high"] == {"20260702": 12.0}
    assert market_data["low"] == {"20260702": 10.4}
    assert market_data["close"] == {"20260702": 11.8}
    assert market_data["volume"] == {"20260702": 456.0}
    assert market_data["amount"] == {"20260702": 0.0}
    assert result["source"] == "local_dat"


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

    result = reader.read_market_data(
        ["000001.SZ"],
        period="1m",
        start_time="2026-07-01T09:31:00+08:00",
        end_time="2026-07-01T09:32:00+08:00",
        count=None,
        fields=["open", "close", "volume", "amount"],
        include_raw=False,
    )

    market_data = result["marketData"]["000001.SZ"]
    assert market_data["open"]["20260701093100"] == 10.29
    assert market_data["close"]["20260701093200"] == 10.38
    assert market_data["volume"]["20260701093100"] == 1200.0
    assert market_data["amount"]["20260701093100"] == 12345.6


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

    result = reader.read_market_data(
        ["000001.SZ"],
        period="5m",
        start_time=None,
        end_time=None,
        count=1,
        fields=["close"],
        include_raw=True,
    )

    assert result["marketData"]["000001.SZ"]["close"] == {"20260701093500": 10.38}
    assert result["rawMeta"]["symbols"]["000001.SZ"]["period_code"] == "300"
    assert result["rawMeta"]["symbols"]["000001.SZ"]["record_size"] == 40
    assert result["rawMeta"]["symbols"]["000001.SZ"]["struct_format"] == "<QIIIIdd"


def test_dat_read_after_block_time_returns_retryable_error(tmp_path: Path) -> None:
    reader = QmtLocalDatReader(
        data_dir=tmp_path,
        enabled=True,
        now=lambda: datetime(2026, 7, 5, 18, 1, tzinfo=BEIJING_TZ),
        on_block="retryable_error",
        stability_wait_ms=0,
    )

    with pytest.raises(QmtLocalDatError) as exc_info:
        reader.read_market_data(
            ["000001.SZ"],
            period="1d",
            start_time=None,
            end_time=None,
            count=1,
            fields=[],
            include_raw=False,
        )

    assert exc_info.value.code == "QMT_LOCAL_DAT_BLOCKED"
    assert exc_info.value.retryable is True
    assert exc_info.value.details["blockAfter"] == "18:00"
