import asyncio
from typing import Any, cast

from src.datasource.contracts import normalize_nullable_k_decimal
from src.datasource.qmt.realtime.gateway import QmtCommandGateway, QmtCommandResult


class QmtBridgeError(Exception):
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


class QmtMarketOperations:
    async def get_bars(
        self,
        stock_list: list[str],
        *,
        period: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
        fields: list[str] | None = None,
        dividend_type: str | None = None,
        fill_data: bool | None = None,
        include_raw: bool = False,
        command_gateway: QmtCommandGateway | None = None,
        bridge_timeout_seconds: float = 10.0,
    ) -> dict[str, object]:
        if command_gateway is None:
            raise QmtBridgeError(
                code="QMT_BRIDGE_UNAVAILABLE",
                message="QMT command gateway is not initialized",
                retryable=True,
            )

        bridge_health = command_gateway.health()
        if bridge_health.get("ownerId") is None:
            raise QmtBridgeError(
                code="QMT_BRIDGE_OWNER_MISSING",
                message="QMT bridge owner is not registered",
                retryable=True,
                details={"bridge": bridge_health},
            )
        if bridge_health.get("ownerStale") or not bridge_health.get("ready"):
            raise QmtBridgeError(
                code="QMT_BRIDGE_OWNER_STALE",
                message="QMT bridge owner heartbeat is stale",
                retryable=True,
                details={"bridge": bridge_health},
            )

        params = {
            "fields": list(fields or []),
            "stock_list": list(stock_list),
            "period": period,
            "start_time": start_time or "",
            "end_time": end_time or "",
            "count": count if count is not None else -1,
            "dividend_type": dividend_type or "none",
            "fill_data": True if fill_data is None else bool(fill_data),
        }
        command = command_gateway.enqueue(
            "get_market_data_ex",
            params,
            timeout_seconds=bridge_timeout_seconds,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + bridge_timeout_seconds

        while loop.time() < deadline:
            command_gateway.expire_timed_out()
            result = command_gateway.take_result(command.command_id)
            if result is None:
                await asyncio.sleep(0.05)
                continue
            return _resolve_bridge_result(
                result,
                command_id=command.command_id,
                include_raw=include_raw,
            )

        command_gateway.expire_timed_out()
        result = command_gateway.take_result(command.command_id)
        if result is not None:
            return _resolve_bridge_result(
                result,
                command_id=command.command_id,
                include_raw=include_raw,
            )

        raise QmtBridgeError(
            code="QMT_BRIDGE_COMMAND_TIMEOUT",
            message="QMT bridge command result timed out",
            retryable=True,
            details={
                "method": "get_market_data_ex",
                "timeoutSeconds": bridge_timeout_seconds,
            },
        )

    async def collect_recent_bars(
        self,
        stock_list: list[str],
        period: str,
        count: int,
        *,
        command_gateway: QmtCommandGateway | None = None,
    ) -> dict[str, object]:
        return await self.get_bars(
            stock_list,
            period=period,
            start_time=None,
            end_time=None,
            count=count,
            command_gateway=command_gateway,
        )


def _dict_details(value: Any) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    mapping = cast(dict[Any, Any], value)
    if not all(isinstance(key, str) for key in mapping):
        return {}
    return cast(dict[str, object], mapping)


def _resolve_bridge_result(
    result: QmtCommandResult,
    *,
    command_id: str,
    include_raw: bool,
) -> dict[str, object]:
    if not result.ok:
        error = result.error or {}
        raise QmtBridgeError(
            code=str(error.get("code") or "QMT_BRIDGE_COMMAND_FAILED"),
            message=str(error.get("message") or "QMT bridge command failed"),
            retryable=bool(error.get("retryable", True)),
            details=_dict_details(error.get("details")),
        )
    return _normalize_bridge_market_data(
        result.result,
        command_id=command_id,
        include_raw=include_raw,
    )


def _normalize_bridge_market_data(
    value: Any,
    *,
    command_id: str,
    include_raw: bool,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise QmtBridgeError(
            code="QMT_BRIDGE_INVALID_MARKET_DATA",
            message="QMT bridge get_market_data_ex result is not a JSON object",
            retryable=True,
            details={"resultType": type(value).__name__},
        )

    mapping = cast(dict[Any, Any], value)
    if not all(isinstance(key, str) for key in mapping):
        raise QmtBridgeError(
            code="QMT_BRIDGE_INVALID_MARKET_DATA",
            message="QMT bridge result contains non-string object keys",
            retryable=True,
            details={},
        )
    bridge_value = cast(dict[str, object], mapping)
    market_data_value = bridge_value.get("marketData", bridge_value)
    if not isinstance(market_data_value, dict):
        raise QmtBridgeError(
            code="QMT_BRIDGE_INVALID_MARKET_DATA",
            message="QMT bridge get_market_data_ex result has no market-data mapping",
            retryable=True,
            details={"resultKeys": sorted(bridge_value)},
        )

    try:
        normalized_market_data = _normalize_historical_measures(
            cast(dict[Any, Any], market_data_value)
        )
    except ValueError as exc:
        raise QmtBridgeError(
            code="QMT_BRIDGE_DECIMAL_OUT_OF_RANGE",
            message=str(exc),
            retryable=True,
            details={},
        ) from exc

    result: dict[str, object] = {
        "marketData": normalized_market_data,
        "source": "native_bridge",
    }
    if include_raw:
        result["rawMeta"] = {
            "source": "native_bridge",
            "method": "get_market_data_ex",
            "commandId": command_id,
        }
    return result


def _normalize_historical_measures(
    market_data: dict[Any, Any],
) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for symbol, symbol_value in market_data.items():
        if not isinstance(symbol, str) or not isinstance(symbol_value, dict):
            normalized[str(symbol)] = symbol_value
            continue
        fields: dict[str, object] = {}
        symbol_mapping = cast(dict[Any, Any], symbol_value)
        for field_name, field_value in symbol_mapping.items():
            key = str(field_name)
            if key.lower() not in {"volume", "amount"}:
                fields[key] = field_value
                continue
            if isinstance(field_value, dict):
                field_mapping = cast(dict[Any, Any], field_value)
                fields[key] = {
                    str(row_key): normalize_nullable_k_decimal(row_value)
                    for row_key, row_value in field_mapping.items()
                }
            elif isinstance(field_value, list):
                field_list = cast(list[Any], field_value)
                fields[key] = [
                    normalize_nullable_k_decimal(row_value) for row_value in field_list
                ]
            else:
                fields[key] = normalize_nullable_k_decimal(field_value)
        normalized[symbol] = fields
    return normalized
