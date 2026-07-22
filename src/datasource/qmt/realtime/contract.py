"""QMT realtime wire constants, symbol rules, and native validation."""

import re
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")
CN_REALTIME_MARKETS = {"SH", "SZ", "BJ"}
HK_REALTIME_MARKETS = {"HK"}
QMT_REALTIME_PAYLOAD_TYPE = "mist.realtime.native_snapshot"
QMT_REALTIME_SCHEMA_VERSION = 1
QMT_REALTIME_ACQUISITION_PROFILE = "qmt.get_full_tick"
QMT_REALTIME_MAX_SUBSCRIPTIONS = 5
QMT_SYMBOL_PATTERN = re.compile(r"^(?:\d{6}\.(?:SH|SZ|BJ)|\d{5,6}\.HK)$")


def is_realtime_trading_session(now: datetime, symbols: list[str]) -> bool:
    if now.weekday() >= 5:
        return False
    markets = _markets_from_symbols(symbols)
    return any(_is_market_realtime_session(now, market) for market in markets)


def as_beijing(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=BEIJING_TZ)
    return value.astimezone(BEIJING_TZ)


def is_valid_snapshot(value: Any, now: datetime) -> bool:
    if not isinstance(value, dict):
        return False
    required = (
        "timetag",
        "lastPrice",
        "open",
        "high",
        "low",
        "lastClose",
        "volume",
        "amount",
    )
    if any(field not in value for field in required):
        return False
    snapshot = cast(dict[str, Any], value)
    try:
        timetag = _parse_qmt_timetag(snapshot["timetag"])
        numbers = {
            field: float(snapshot[field]) for field in required if field != "timetag"
        }
    except (TypeError, ValueError):
        return False
    return (
        timetag.date() == now.date()
        and numbers["lastPrice"] > 0
        and numbers["volume"] >= 0
        and numbers["amount"] >= 0
        and all(
            number == number and abs(number) != float("inf")
            for number in numbers.values()
        )
    )


def _markets_from_symbols(symbols: list[str]) -> set[str]:
    markets: set[str] = set()
    for symbol in symbols:
        suffix = str(symbol).upper().strip().rsplit(".", 1)[-1]
        if suffix in CN_REALTIME_MARKETS:
            markets.add("CN")
        elif suffix in HK_REALTIME_MARKETS:
            markets.add("HK")
    return markets or {"UNKNOWN"}


def _is_market_realtime_session(now: datetime, market: str) -> bool:
    value = now.hour * 60 + now.minute
    if market == "CN":
        return _in_minutes(value, 9, 15, 11, 35) or _in_minutes(value, 13, 0, 15, 5)
    if market == "HK":
        return _in_minutes(value, 9, 0, 12, 5) or _in_minutes(value, 13, 0, 16, 10)
    return _in_minutes(value, 9, 0, 16, 10)


def _in_minutes(value: int, sh: int, sm: int, eh: int, em: int) -> bool:
    return sh * 60 + sm <= value <= eh * 60 + em


def _parse_qmt_timetag(value: Any) -> datetime:
    text = str(value).strip()
    for format_string in ("%Y%m%d%H%M%S", "%Y%m%d %H:%M:%S"):
        try:
            return datetime.strptime(text, format_string)
        except ValueError:
            continue
    raise ValueError(f"unsupported QMT timetag: {text}")
