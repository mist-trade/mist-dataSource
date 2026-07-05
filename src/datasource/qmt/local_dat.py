import struct
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.core.config import settings
from src.datasource.contracts import BEIJING_TZ, normalize_beijing_iso
from src.datasource.tdx_models import TdxBar
from src.datasource.tdx_normalization import beijing_iso, normalize_symbol

PERIOD_CODES = {
    "1d": "86400",
    "1m": "60",
    "5m": "300",
}

DAILY_HEADER_SIZE = 8
DAILY_RECORD_SIZE = 32
MIN_VALID_TS = 631152000
MAX_VALID_TS = 2051222400


@dataclass(frozen=True)
class _DatBar:
    symbol: str
    period: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


@dataclass(frozen=True)
class _MinuteFormat:
    struct_format: str
    price_scale: float
    field_names: tuple[str, ...]

    @property
    def record_size(self) -> int:
        return struct.calcsize(self.struct_format)


MINUTE_FORMATS = (
    _MinuteFormat("<QIIIIdd", 10000.0, ("time", "open", "high", "low", "close", "volume", "amount")),
)


class QmtLocalDatError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class QmtLocalDatReader:
    def __init__(
        self,
        *,
        data_dir: str | Path = "",
        enabled: bool = False,
        periods: Iterable[str] | None = None,
        block_after: str = "18:00",
        now: Callable[[], datetime] | None = None,
        on_block: str = "fallback_bridge",
        stability_wait_ms: int = 500,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.enabled = enabled
        self.periods = frozenset(periods or PERIOD_CODES)
        self.block_after = block_after
        self.now = now or datetime.now
        self.on_block = on_block
        self.stability_wait_ms = stability_wait_ms

    @classmethod
    def from_settings(cls) -> "QmtLocalDatReader":
        periods = [period.strip() for period in settings.qmt.local_dat_periods.split(",")]
        return cls(
            data_dir=settings.qmt.local_dat_dir,
            enabled=settings.qmt.local_dat_enabled,
            periods=[period for period in periods if period],
            block_after=settings.qmt.local_dat_block_after,
            on_block=settings.qmt.local_dat_on_block,
            stability_wait_ms=settings.qmt.local_dat_stability_wait_ms,
        )

    def read_bars(
        self,
        symbols: list[str],
        *,
        period: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
    ) -> list[TdxBar]:
        self._ensure_can_read(period)
        start_dt = _parse_filter_time(start_time)
        end_dt = _parse_filter_time(end_time)
        received_at = self.now()

        bars: list[TdxBar] = []
        for symbol in symbols:
            normalized_symbol = normalize_symbol(symbol)
            file_path = self._resolve_path(normalized_symbol, period)
            raw = self._read_stable_file(file_path)
            parsed = self._parse_file(raw, normalized_symbol, period)
            filtered = [
                item
                for item in sorted(parsed, key=lambda item: item.timestamp)
                if _within_range(item.timestamp, start_dt, end_dt)
            ]
            if count is not None:
                filtered = filtered[-max(count, 0) :]
            bars.extend(_to_tdx_bar(item, received_at) for item in filtered)
        return bars

    def _ensure_can_read(self, period: str) -> None:
        if not self.enabled:
            raise _error(
                code="QMT_LOCAL_DAT_DISABLED",
                message="QMT local DAT reader is disabled",
                details={"period": period},
            )
        if not str(self.data_dir):
            raise _error(
                code="QMT_LOCAL_DAT_DIR_MISSING",
                message="QMT local DAT directory is not configured",
                details={"period": period},
            )
        if period not in self.periods or period not in PERIOD_CODES:
            raise _error(
                code="QMT_LOCAL_DAT_UNSUPPORTED_PERIOD",
                message=f"QMT local DAT period is not supported: {period}",
                retryable=False,
                details={"period": period, "supportedPeriods": sorted(self.periods & PERIOD_CODES.keys())},
            )
        if self._is_blocked_by_time():
            raise _error(
                code="QMT_LOCAL_DAT_BLOCKED",
                message="QMT local DAT read is blocked by the configured update window",
                details={
                    "blockAfter": self.block_after,
                    "onBlock": self.on_block,
                    "period": period,
                },
            )

    def _is_blocked_by_time(self) -> bool:
        hour_text, minute_text = self.block_after.split(":", 1)
        block_hour = int(hour_text)
        block_minute = int(minute_text)
        now = self.now()
        now = now.replace(tzinfo=BEIJING_TZ) if now.tzinfo is None else now.astimezone(BEIJING_TZ)
        return (now.hour, now.minute) >= (block_hour, block_minute)

    def _resolve_path(self, symbol: str, period: str) -> Path:
        if "." not in symbol:
            raise _error(
                code="QMT_LOCAL_DAT_SYMBOL_INVALID",
                message=f"QMT local DAT symbol must include market suffix: {symbol}",
                retryable=False,
                details={"symbol": symbol},
            )
        code, market = symbol.split(".", 1)
        path = self.data_dir / market / PERIOD_CODES[period] / f"{code}.DAT"
        if not path.exists():
            raise _error(
                code="QMT_LOCAL_DAT_FILE_NOT_FOUND",
                message=f"QMT local DAT file not found for {symbol} {period}",
                details={"symbol": symbol, "period": period, "path": str(path)},
            )
        return path

    def _read_stable_file(self, path: Path) -> bytes:
        before = path.stat()
        if self.stability_wait_ms > 0:
            time.sleep(self.stability_wait_ms / 1000.0)
        after = path.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise _error(
                code="QMT_LOCAL_DAT_FILE_UNSTABLE",
                message="QMT local DAT file changed during stability check",
                details={"path": str(path)},
            )
        return path.read_bytes()

    def _parse_file(self, raw: bytes, symbol: str, period: str) -> list[_DatBar]:
        if period == "1d":
            return _parse_daily(raw, symbol)
        return _parse_minute(raw, symbol, period)


def _parse_daily(raw: bytes, symbol: str) -> list[_DatBar]:
    if len(raw) < DAILY_HEADER_SIZE + DAILY_RECORD_SIZE:
        raise _error(
            code="QMT_LOCAL_DAT_FORMAT_UNSUPPORTED",
            message="QMT daily DAT file is too small",
            details={"symbol": symbol, "recordSize": DAILY_RECORD_SIZE, "headerSize": DAILY_HEADER_SIZE},
        )

    data = raw[DAILY_HEADER_SIZE:]
    total_records = len(data) // DAILY_RECORD_SIZE
    bars: list[_DatBar] = []
    for index in range(0, total_records, 2):
        offset = index * DAILY_RECORD_SIZE
        ts, open_p, high_p, low_p, close_p, _reserved, volume_lots, _market = struct.unpack_from(
            "<IIIIIIII",
            data,
            offset,
        )
        if not _is_valid_timestamp(ts):
            continue
        open_value = open_p / 1000.0
        high_value = high_p / 1000.0
        low_value = low_p / 1000.0
        close_value = close_p / 1000.0
        if not _is_valid_ohlc(open_value, high_value, low_value, close_value):
            continue
        bars.append(
            _DatBar(
                symbol=symbol,
                period="1d",
                timestamp=datetime.fromtimestamp(ts, BEIJING_TZ),
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                volume=volume_lots * 100.0,
                amount=0.0,
            )
        )
    return bars


def _parse_minute(raw: bytes, symbol: str, period: str) -> list[_DatBar]:
    attempts: list[dict[str, Any]] = []
    for minute_format in MINUTE_FORMATS:
        record_size = minute_format.record_size
        if len(raw) < record_size:
            attempts.append({"recordSize": record_size, "format": minute_format.struct_format, "headerSize": None})
            continue
        header_size = len(raw) % record_size
        record_count = len(raw) // record_size
        if record_count <= 0:
            attempts.append({"recordSize": record_size, "format": minute_format.struct_format, "headerSize": header_size})
            continue
        try:
            bars = _parse_minute_with_format(
                raw[header_size:],
                symbol,
                period,
                minute_format,
                record_count,
            )
        except (struct.error, ValueError) as exc:
            attempts.append(
                {
                    "recordSize": record_size,
                    "format": minute_format.struct_format,
                    "headerSize": header_size,
                    "error": str(exc),
                }
            )
            continue
        if bars:
            return bars
        attempts.append({"recordSize": record_size, "format": minute_format.struct_format, "headerSize": header_size})

    raise _error(
        code="QMT_LOCAL_DAT_FORMAT_UNSUPPORTED",
        message=f"QMT minute DAT format is not supported for {symbol} {period}",
        details={"symbol": symbol, "period": period, "attempts": attempts},
    )


def _parse_minute_with_format(
    data: bytes,
    symbol: str,
    period: str,
    minute_format: _MinuteFormat,
    record_count: int,
) -> list[_DatBar]:
    bars: list[_DatBar] = []
    offset = 0
    for _index in range(record_count):
        values = struct.unpack_from(minute_format.struct_format, data, offset)
        offset += minute_format.record_size
        ts_raw = int(values[0])
        ts = ts_raw // 1000 if ts_raw > 1_000_000_000_000 else ts_raw
        if not _is_valid_timestamp(ts):
            raise ValueError(f"invalid timestamp: {ts_raw}")
        timestamp = datetime.fromtimestamp(ts, BEIJING_TZ)
        open_value = float(values[1]) / minute_format.price_scale
        high_value = float(values[2]) / minute_format.price_scale
        low_value = float(values[3]) / minute_format.price_scale
        close_value = float(values[4]) / minute_format.price_scale
        volume = float(values[5])
        amount = float(values[6])
        if not _is_valid_ohlc(open_value, high_value, low_value, close_value):
            raise ValueError("invalid OHLC values")
        if volume < 0 or amount < 0:
            raise ValueError("invalid volume or amount")
        if period == "5m" and timestamp.minute % 5 != 0:
            raise ValueError("timestamp is not aligned to 5m period")
        bars.append(
            _DatBar(
                symbol=symbol,
                period=period,
                timestamp=timestamp,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                volume=volume,
                amount=amount,
            )
        )
    return sorted(bars, key=lambda item: item.timestamp)


def _parse_filter_time(value: str | None) -> datetime | None:
    normalized = normalize_beijing_iso(value)
    if normalized is None:
        return None
    return datetime.fromisoformat(normalized)


def _within_range(
    timestamp: datetime,
    start_time: datetime | None,
    end_time: datetime | None,
) -> bool:
    if start_time is not None and timestamp < start_time:
        return False
    return not (end_time is not None and timestamp > end_time)


def _to_tdx_bar(item: _DatBar, received_at: datetime) -> TdxBar:
    return TdxBar(
        symbol=item.symbol,
        period=item.period,
        barTime=beijing_iso(item.timestamp),
        open=item.open,
        high=item.high,
        low=item.low,
        close=item.close,
        volume=item.volume,
        amount=item.amount,
        provider="qmt",
        receivedAt=beijing_iso(received_at),
    )


def _is_valid_timestamp(value: int) -> bool:
    return MIN_VALID_TS < value < MAX_VALID_TS


def _is_valid_ohlc(open_value: float, high_value: float, low_value: float, close_value: float) -> bool:
    if open_value <= 0 or close_value <= 0:
        return False
    if high_value < low_value:
        return False
    if min(open_value, high_value, low_value, close_value) <= 0:
        return False
    return not (max(open_value, high_value, low_value, close_value) > 100000)


def _error(
    *,
    code: str,
    message: str,
    retryable: bool = True,
    details: dict[str, object] | None = None,
) -> QmtLocalDatError:
    return QmtLocalDatError(
        code=code,
        message=message,
        retryable=retryable,
        details=details,
    )
