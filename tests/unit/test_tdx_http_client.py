import json
from typing import Any

import httpx
import pytest

from src.datasource.tdx.http_client import TdxHttpClient, TdxHttpError


@pytest.mark.asyncio
async def test_call_posts_json_rpc_payload_and_returns_result():
    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.read()))
        return httpx.Response(200, json={"result": {"ok": True}})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    result = await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    assert result == {"ok": True}
    assert len(requests) == 1
    payload = requests[0]
    assert payload["jsonrpc"] == "2.0"
    assert payload["method"] == "get_market_snapshot"
    assert payload["params"] == {"stock_code": "SH600519"}
    assert "id" in payload

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_raises_retryable_error_for_json_rpc_error_response():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "error": {
                    "code": -32000,
                    "message": "native call failed",
                    "data": {"method": "get_market_snapshot"},
                }
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is True
    assert "native call failed" in error.message
    assert error.details["error"]["code"] == -32000

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_json_rpc_method_not_found_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"code": -32601, "message": "Method not found"}},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("missing_method", {})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False
    assert error.details["error"]["code"] == -32601

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_json_rpc_invalid_params_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"code": -32602, "message": "Invalid params"}},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"bad": True})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False
    assert error.details["error"]["code"] == -32602

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_keeps_json_rpc_provider_error_retryable():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"code": -32000, "message": "native temporary failure"}},
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is True
    assert error.details["error"]["code"] == -32000

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_json_list_body_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False
    assert error.details["body_type"] == "list"

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_json_null_body_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"null")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False
    assert error.details["body_type"] == "NoneType"

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_json_object_without_result_or_error_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "x"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False
    assert error.details["reason"] == "missing_result"
    assert error.details["body"] == {"jsonrpc": "2.0", "id": "x"}

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_invalid_json_body_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_raises_retryable_unavailable_error_for_httpx_request_errors():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_UNAVAILABLE"
    assert error.retryable is True
    assert "connection refused" in error.message

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_http_400_to_non_retryable_contract_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_ERROR"
    assert error.retryable is False
    assert error.details["status_code"] == 400

    await http_client.aclose()


@pytest.mark.asyncio
async def test_call_maps_http_503_to_retryable_unavailable_error():
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = TdxHttpClient("http://tdx.local/", http_client=http_client)

    with pytest.raises(TdxHttpError) as exc_info:
        await client.call("get_market_snapshot", {"stock_code": "SH600519"})

    error = exc_info.value
    assert error.code == "TDX_HTTP_UNAVAILABLE"
    assert error.retryable is True
    assert error.details["status_code"] == 503

    await http_client.aclose()


@pytest.mark.asyncio
async def test_aclose_closes_owned_client():
    client = TdxHttpClient("http://tdx.local/")
    owned_http_client = client.http_client

    await client.aclose()

    assert owned_http_client.is_closed is True


@pytest.mark.asyncio
async def test_aclose_does_not_close_injected_client():
    external_http_client = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200)))
    client = TdxHttpClient("http://tdx.local/", http_client=external_http_client)

    await client.aclose()

    assert external_http_client.is_closed is False

    await external_http_client.aclose()
