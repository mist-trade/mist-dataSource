from datetime import datetime, timedelta, timezone
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

BEIJING_TZ = timezone(timedelta(hours=8))


def normalize_beijing_iso(value: str | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))

    dt = dt.replace(tzinfo=BEIJING_TZ) if dt.tzinfo is None else dt.astimezone(BEIJING_TZ)
    return dt.isoformat()


class DatasourceModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)


class DatasourceError(DatasourceModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ResponseMeta(DatasourceModel):
    source_latency_ms: int | None = Field(default=None, alias="sourceLatencyMs")
    transport: str
    as_of: str = Field(alias="asOf")
    request_key: str | None = Field(default=None, alias="requestKey")

    @field_validator("as_of", mode="before")
    @classmethod
    def normalize_as_of(cls, value: str | datetime) -> str:
        normalized = normalize_beijing_iso(value)
        if normalized is None:
            msg = "asOf is required"
            raise ValueError(msg)
        return normalized


class ResponseEnvelope(DatasourceModel):
    ok: bool
    request_id: str = Field(alias="requestId")
    provider: str
    data: Any | None = None
    meta: ResponseMeta | None = None
    error: DatasourceError | None = None

    @classmethod
    def success(
        cls,
        *,
        request_id: str,
        provider: str,
        data: Any,
        meta: ResponseMeta | None = None,
    ) -> "ResponseEnvelope":
        return cls(
            ok=True,
            requestId=request_id,
            provider=provider,
            data=data,
            meta=meta,
            error=None,
        )

    @classmethod
    def failure(
        cls,
        *,
        request_id: str,
        provider: str,
        error: DatasourceError,
        meta: ResponseMeta | None = None,
    ) -> "ResponseEnvelope":
        return cls(
            ok=False,
            requestId=request_id,
            provider=provider,
            data=None,
            meta=meta,
            error=error,
        )


def serialize_response_data(value: Any) -> Any:
    """Serialize nested datasource models once at the response boundary."""
    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True)
    if isinstance(value, list):
        return [serialize_response_data(item) for item in cast(list[Any], value)]
    if isinstance(value, dict):
        mapping = cast(dict[Any, Any], value)
        return {str(key): serialize_response_data(item) for key, item in mapping.items()}
    return value
