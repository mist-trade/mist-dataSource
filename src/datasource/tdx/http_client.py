from typing import Any, cast
from uuid import uuid4

import httpx

JSON_RPC_STANDARD_ERROR_CODES = {-32700, -32600, -32601, -32602, -32603}


class TdxHttpError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class TdxHttpClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient()

    @property
    def http_client(self) -> httpx.AsyncClient:
        return self._http_client

    async def call(self, method: str, params: dict[str, Any] | list[Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid4()),
            "method": method,
            "params": params if params is not None else {},
        }

        try:
            response = await self._http_client.post(
                self.base_url,
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.RequestError as exc:
            raise TdxHttpError(
                code="TDX_HTTP_UNAVAILABLE",
                message=str(exc),
                retryable=True,
                details={"url": self.base_url, "method": method},
            )
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            retryable = status_code in {408, 429} or status_code >= 500
            code = "TDX_HTTP_UNAVAILABLE" if retryable else "TDX_HTTP_ERROR"
            raise TdxHttpError(
                code=code,
                message=str(exc),
                retryable=retryable,
                details={
                    "url": self.base_url,
                    "method": method,
                    "status_code": status_code,
                },
            )
        except ValueError as exc:
            raise TdxHttpError(
                code="TDX_HTTP_ERROR",
                message=str(exc),
                retryable=False,
                details={"url": self.base_url, "method": method},
            )

        if not isinstance(body, dict):
            raise TdxHttpError(
                code="TDX_HTTP_ERROR",
                message="TDX HTTP response body must be a JSON object",
                retryable=False,
                details={
                    "url": self.base_url,
                    "method": method,
                    "body_type": type(body).__name__,
                    "body": body,
                },
            )
        body_map = cast(dict[str, Any], body)

        if "error" in body_map and body_map["error"] is not None:
            error = body_map["error"]
            if isinstance(error, dict):
                error_map = cast(dict[str, Any], error)
                message = str(error_map.get("message", str(error_map)))
            else:
                message = str(error)
            retryable = _json_rpc_error_retryable(error)
            raise TdxHttpError(
                code="TDX_HTTP_ERROR",
                message=message,
                retryable=retryable,
                details={"url": self.base_url, "method": method, "error": error},
            )

        if "result" not in body_map:
            raise TdxHttpError(
                code="TDX_HTTP_ERROR",
                message="TDX HTTP response body is missing JSON-RPC result",
                retryable=False,
                details={
                    "url": self.base_url,
                    "method": method,
                    "reason": "missing_result",
                    "body": body_map,
                },
            )

        return body_map["result"]

    async def aclose(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()


def _json_rpc_error_retryable(error: Any) -> bool:
    if not isinstance(error, dict):
        return True

    error_map = cast(dict[str, Any], error)
    error_code = error_map.get("code")
    if error_code in JSON_RPC_STANDARD_ERROR_CODES:
        return False
    if isinstance(error_code, int) and -32099 <= error_code <= -32000:
        return True
    return True
