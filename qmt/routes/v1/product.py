from datetime import datetime
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from src.datasource.contracts import BEIJING_TZ, DatasourceError, ResponseEnvelope, ResponseMeta
from src.datasource.qmt.local_dat import QmtLocalDatError
from src.datasource.qmt_provider import QmtDatasourceProvider

router = APIRouter()


class QmtV1Model(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class QmtBarQueryRequest(QmtV1Model):
    fields: list[str] = Field(default_factory=list)
    stock_list: list[str]
    period: str = "1d"
    start_time: str = ""
    end_time: str = ""
    count: int = -1
    dividend_type: str = "none"
    fill_data: bool = True
    include_raw: bool = False


def _get_provider(request: Request) -> QmtDatasourceProvider | None:
    provider = getattr(request.app.state, "qmt_provider", None)
    if isinstance(provider, QmtDatasourceProvider):
        return provider
    return None


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id") or str(uuid4())


def _meta() -> ResponseMeta:
    return ResponseMeta(transport="http", asOf=datetime.now(BEIJING_TZ).isoformat())


def _dump(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True)
    if isinstance(value, list):
        return [_dump(item) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        return {str(key): _dump(item) for key, item in cast(dict[Any, Any], value).items()}
    return value


def _success(request: Request, data: Any) -> ResponseEnvelope:
    return ResponseEnvelope.success(
        request_id=_request_id(request),
        provider="qmt",
        data=_dump(data),
        meta=_meta(),
    )


def _failure(request: Request, exc: Exception) -> ResponseEnvelope:
    return ResponseEnvelope.failure(
        request_id=_request_id(request),
        provider="qmt",
        error=_to_datasource_error(exc),
        meta=_meta(),
    )


def _to_datasource_error(exc: Exception) -> DatasourceError:
    if isinstance(exc, DatasourceError):
        return exc

    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    retryable = getattr(exc, "retryable", None)
    details = getattr(exc, "details", None)
    if code and message is not None and retryable is not None:
        error_details = cast(dict[str, Any], details) if isinstance(details, dict) else {}
        return DatasourceError(
            code=str(code),
            message=str(message),
            retryable=bool(retryable),
            details=error_details,
        )

    return DatasourceError(
        code="QMT_PROVIDER_ERROR",
        message=str(exc),
        retryable=False,
        details={"exception": type(exc).__name__},
    )


def _provider_unavailable() -> DatasourceError:
    return DatasourceError(
        code="QMT_PROVIDER_UNAVAILABLE",
        message="QMT datasource provider is not initialized",
        retryable=True,
        details={},
    )


@router.post("/v1/bars/query")
async def query_bars(payload: QmtBarQueryRequest, request: Request):
    provider = _get_provider(request)
    if provider is None:
        return ResponseEnvelope.failure(
            request_id=_request_id(request),
            provider="qmt",
            error=_provider_unavailable(),
            meta=_meta(),
        )

    try:
        result = await provider.get_bars(
            stock_list=payload.stock_list,
            period=payload.period,
            start_time=payload.start_time,
            end_time=payload.end_time,
            count=payload.count,
            fields=payload.fields,
            dividend_type=payload.dividend_type,
            fill_data=payload.fill_data,
            include_raw=payload.include_raw,
        )
    except QmtLocalDatError as exc:
        return _failure(request, exc)
    return _success(request, result)
