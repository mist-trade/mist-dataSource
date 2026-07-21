from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from src.datasource.tdx_http_client import TdxHttpError
from src.datasource.tdx_models import TdxBar, TdxSnapshot
from tdx.main import app
from tdx.routes.v1 import product as tdx_v1_routes


class FakeTdxProvider:
    def __init__(self) -> None:
        self.bar_queries: list[dict[str, Any]] = []
        self.raw_calls: list[tuple[str, dict[str, Any]]] = []
        self.sector_queries: list[str] = []
        self.sector_list_queries: list[int] = []
        self.security_list_queries: list[str] = []
        self.security_info_queries: list[list[str]] = []
        self.trading_date_queries: list[tuple[str, str | None, str | None, int | None]] = []
        self.price_volume_queries: list[tuple[list[str], list[str] | None]] = []
        self.relation_queries: list[str] = []
        self.ipo_queries: list[tuple[int, int]] = []
        self.share_capital_queries: list[tuple[str, list[str], int]] = []
        self.share_capital_by_date_queries: list[tuple[str, str, str]] = []
        self.dividend_factor_queries: list[tuple[str, str | None, str | None]] = []
        self.convertible_bond_queries: list[tuple[str, list[str] | None, str]] = []
        self.track_etf_queries: list[str] = []
        self.financial_data_queries: list[tuple[list[str], list[str], str, str, str]] = []
        self.financial_data_by_date_queries: list[tuple[list[str], list[str], int, int]] = []
        self.single_finance_value_queries: list[tuple[list[str], list[str]]] = []
        self.stock_trade_aggregate_queries: list[tuple[list[str], list[str], str, str]] = []
        self.stock_trade_aggregate_by_date_queries: list[tuple[list[str], list[str], int, int]] = []
        self.sector_trade_aggregate_queries: list[tuple[list[str], list[str], str, str]] = []
        self.sector_trade_aggregate_by_date_queries: list[
            tuple[list[str], list[str], int, int]
        ] = []
        self.market_trade_aggregate_queries: list[tuple[list[str], str, str]] = []
        self.market_trade_aggregate_by_date_queries: list[tuple[list[str], int, int]] = []
        self.formula_format_queries: list[dict[str, Any]] = []
        self.formula_set_data_queries: list[dict[str, Any]] = []
        self.formula_set_data_info_queries: list[dict[str, Any]] = []
        self.formula_get_data_calls = 0
        self.formula_get_all_queries: list[int] = []
        self.formula_get_info_queries: list[tuple[int, str]] = []
        self.formula_execution_queries: list[tuple[str, str, str, int | None, int]] = []
        self.formula_batch_execution_queries: list[tuple[str, str, list[str], int]] = []
        self.formula_calls: list[tuple[str, Any, Any]] = []
        self.fail_bars = False

    async def get_bars(
        self,
        symbols: list[str],
        *,
        period: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
        fields: list[str] | None = None,
        dividend_type: str = "front",
        fill_data: bool = True,
    ) -> list[TdxBar]:
        self.bar_queries.append(
            {
                "symbols": symbols,
                "period": period,
                "startTime": start_time,
                "endTime": end_time,
                "count": count,
                "fields": fields,
                "dividendType": dividend_type,
                "fillData": fill_data,
            }
        )
        if self.fail_bars:
            raise TdxHttpError(
                code="TDX_HTTP_UNAVAILABLE",
                message="TDX HTTP is unavailable",
                retryable=True,
                details={"method": "get_market_data"},
            )

        return [
            TdxBar(
                symbol=symbols[0],
                period=period,
                barTime="2026-04-06T09:31:00+08:00",
                open=1.0,
                high=2.0,
                low=0.5,
                close=1.5,
                volume=1000,
                amount=1500,
                receivedAt=datetime(2026, 4, 6, 9, 31, tzinfo=UTC),
            )
        ][: count or 1]

    async def get_snapshots(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[TdxSnapshot]:
        _ = fields
        return [
            TdxSnapshot(
                symbol=symbols[0],
                last=10.0,
                open=9.8,
                high=10.2,
                low=9.7,
                lastClose=9.6,
                volume=10000,
                amount=100000,
                asOf="2026-04-06T10:00:00+08:00",
            )
        ]

    async def raw_call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.raw_calls.append((method, params))
        return {"method": method, "params": params}

    async def get_sector_members(self, sector: str) -> list[str]:
        self.sector_queries.append(sector)
        return ["600519.SH", "000001.SZ"]

    async def get_sector_list(self, list_type: int = 0) -> list[dict[str, Any]]:
        self.sector_list_queries.append(list_type)
        return [
            {"code": "880081.SH", "name": "通达信88", "provider": "tdx"},
            {"code": "880300.SH", "name": "沪深300", "provider": "tdx"},
        ]

    async def get_trading_dates(
        self,
        market: str,
        start_time: str | None,
        end_time: str | None,
        count: int | None,
    ) -> list[str]:
        self.trading_date_queries.append((market, start_time, end_time, count))
        return ["2026-06-25", "2026-06-26"]

    async def get_securities(self, market: str) -> list[dict[str, Any]]:
        self.security_list_queries.append(market)
        return [
            {"symbol": "600519.SH", "name": "贵州茅台", "provider": "tdx"},
            {"symbol": "000001.SZ", "name": "平安银行", "provider": "tdx"},
        ]

    async def get_security_info(self, symbols: list[str]) -> list[dict[str, Any]]:
        self.security_info_queries.append(symbols)
        return [
            {
                "symbol": symbols[0],
                "name": "贵州茅台",
                "market": "SH",
                "provider": "tdx",
                "raw": {"Code": symbols[0]},
            }
        ]

    async def get_price_volume(
        self,
        symbols: list[str],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.price_volume_queries.append((symbols, fields))
        return [
            {
                "symbol": symbols[0],
                "price": 1168.63,
                "volume": 1000.0,
                "amount": 1168630.0,
                "provider": "tdx",
            }
        ]

    async def get_security_relations(self, symbol: str) -> list[dict[str, Any]]:
        self.relation_queries.append(symbol)
        return [
            {
                "symbol": symbol,
                "category": "industry",
                "code": "880081.SH",
                "name": "通达信88",
                "provider": "tdx",
            }
        ]

    async def get_ipo_info(self, ipo_type: int, ipo_date: int) -> list[dict[str, Any]]:
        self.ipo_queries.append((ipo_type, ipo_date))
        return [
            {
                "code": "301036.SZ",
                "name": "双乐转债",
                "subscribeCode": "371036",
                "subscribeDate": "20251226",
                "issuePrice": 100.0,
                "provider": "tdx",
            }
        ]

    async def get_share_capital(
        self,
        symbol: str,
        date_list: list[str],
        count: int,
    ) -> list[dict[str, Any]]:
        self.share_capital_queries.append((symbol, date_list, count))
        return [
            {
                "symbol": symbol,
                "date": "20250101",
                "totalShareCapital": 182942480.0,
                "floatShareCapital": 182942480.0,
                "provider": "tdx",
            }
        ]

    async def get_share_capital_by_date(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> list[dict[str, Any]]:
        self.share_capital_by_date_queries.append((symbol, start_date, end_date))
        return [
            {
                "symbol": symbol,
                "date": "20250101",
                "totalShareCapital": 182942480.0,
                "floatShareCapital": 182942480.0,
                "provider": "tdx",
            }
        ]

    async def get_dividend_factors(
        self,
        symbol: str,
        start_time: str | None,
        end_time: str | None,
    ) -> list[dict[str, Any]]:
        self.dividend_factor_queries.append((symbol, start_time, end_time))
        return [
            {
                "symbol": symbol,
                "date": "20250101",
                "type": "1",
                "bonus": 1.23,
                "provider": "tdx",
            }
        ]

    async def get_convertible_bond_info(
        self,
        symbol: str,
        fields: list[str] | None = None,
        native_method: str = "get_kzz_info",
    ) -> list[dict[str, Any]]:
        self.convertible_bond_queries.append((symbol, fields, native_method))
        return [
            {
                "symbol": symbol,
                "bondCode": "123039.SZ",
                "underlyingSymbol": "300577.SZ",
                "convertPrice": 29.15,
                "provider": "tdx",
            }
        ]

    async def get_tracking_etfs(self, index_symbol: str) -> list[dict[str, Any]]:
        self.track_etf_queries.append(index_symbol)
        return [
            {
                "indexSymbol": index_symbol,
                "symbol": "510300.SH",
                "name": "沪深300ETF",
                "price": 4.21,
                "provider": "tdx",
            }
        ]

    async def get_financial_data(
        self,
        symbols: list[str],
        fields: list[str],
        start_time: str,
        end_time: str,
        report_type: str,
    ) -> list[dict[str, Any]]:
        self.financial_data_queries.append((symbols, fields, start_time, end_time, report_type))
        return [
            {
                "symbol": symbols[0],
                "field": fields[0],
                "value": 162.47,
                "announceTime": "20250331",
                "tagTime": "20241231",
                "provider": "tdx",
            }
        ]

    async def get_financial_data_by_date(
        self,
        symbols: list[str],
        fields: list[str],
        year: int,
        mmdd: int,
    ) -> list[dict[str, Any]]:
        self.financial_data_by_date_queries.append((symbols, fields, year, mmdd))
        return [
            {
                "symbol": symbols[0],
                "field": fields[0],
                "value": 69.67,
                "provider": "tdx",
            }
        ]

    async def get_single_finance_values(
        self,
        symbols: list[str],
        fields: list[str],
    ) -> list[dict[str, Any]]:
        self.single_finance_value_queries.append((symbols, fields))
        return [
            {
                "symbol": symbols[0],
                "field": fields[0],
                "value": 107.41,
                "provider": "tdx",
            }
        ]

    async def get_stock_trade_aggregate(
        self,
        symbols: list[str],
        fields: list[str],
        start_time: str,
        end_time: str,
    ) -> list[dict[str, Any]]:
        self.stock_trade_aggregate_queries.append((symbols, fields, start_time, end_time))
        return [
            {
                "scope": "stock",
                "code": symbols[0],
                "field": fields[0],
                "date": "20250102",
                "values": [141405.89, 11113.0],
                "provider": "tdx",
            }
        ]

    async def get_stock_trade_aggregate_by_date(
        self,
        symbols: list[str],
        fields: list[str],
        year: int,
        mmdd: int,
    ) -> list[dict[str, Any]]:
        self.stock_trade_aggregate_by_date_queries.append((symbols, fields, year, mmdd))
        return [
            {
                "scope": "stock",
                "code": symbols[0],
                "field": fields[0],
                "date": None,
                "values": [24154.0, 0.0],
                "provider": "tdx",
            }
        ]

    async def get_sector_trade_aggregate(
        self,
        sector_codes: list[str],
        fields: list[str],
        start_time: str,
        end_time: str,
    ) -> list[dict[str, Any]]:
        self.sector_trade_aggregate_queries.append((sector_codes, fields, start_time, end_time))
        return [
            {
                "scope": "sector",
                "code": sector_codes[0],
                "field": fields[0],
                "date": "20250102",
                "values": [55.28, 55.5],
                "provider": "tdx",
            }
        ]

    async def get_sector_trade_aggregate_by_date(
        self,
        sector_codes: list[str],
        fields: list[str],
        year: int,
        mmdd: int,
    ) -> list[dict[str, Any]]:
        self.sector_trade_aggregate_by_date_queries.append((sector_codes, fields, year, mmdd))
        return [
            {
                "scope": "sector",
                "code": sector_codes[0],
                "field": fields[0],
                "date": None,
                "values": [3.0, 31.0],
                "provider": "tdx",
            }
        ]

    async def get_market_trade_aggregate(
        self,
        fields: list[str],
        start_time: str,
        end_time: str,
    ) -> list[dict[str, Any]]:
        self.market_trade_aggregate_queries.append((fields, start_time, end_time))
        return [
            {
                "scope": "market",
                "code": None,
                "field": fields[0],
                "date": "20250102",
                "values": [184712288.0, 999820.06],
                "provider": "tdx",
            }
        ]

    async def get_market_trade_aggregate_by_date(
        self,
        fields: list[str],
        year: int,
        mmdd: int,
    ) -> list[dict[str, Any]]:
        self.market_trade_aggregate_by_date_queries.append((fields, year, mmdd))
        return [
            {
                "scope": "market",
                "code": None,
                "field": fields[0],
                "date": None,
                "values": [0.0, 181415.13],
                "provider": "tdx",
            }
        ]

    async def format_formula_data(
        self,
        data: dict[str, Any],
        timeout_ms: int = 10000,
    ) -> list[dict[str, Any]]:
        _ = timeout_ms
        self.formula_format_queries.append(data)
        return [{"symbol": "688318.SH", "rows": [{"Close": 144.4}], "provider": "tdx"}]

    async def set_formula_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.formula_set_data_queries.append(payload)
        return {"message": "set ok", "runId": "1", "provider": "tdx"}

    async def set_formula_data_info(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.formula_set_data_info_queries.append(payload)
        return {"message": "set info ok", "runId": "2", "provider": "tdx"}

    async def get_formula_data(self, timeout_ms: int = 10000) -> dict[str, Any]:
        _ = timeout_ms
        self.formula_get_data_calls += 1
        return {"symbol": "688318.SH", "rows": [{"Close": 144.4}], "provider": "tdx"}

    async def get_formula_list(
        self,
        formula_type: int,
        timeout_ms: int = 10000,
    ) -> list[dict[str, Any]]:
        _ = timeout_ms
        self.formula_get_all_queries.append(formula_type)
        return [{"code": "MA", "name": "均线", "type": formula_type, "isSystem": True}]

    async def get_formula_info(
        self,
        formula_type: int,
        formula_code: str,
        timeout_ms: int = 10000,
    ) -> dict[str, Any]:
        _ = timeout_ms
        self.formula_get_info_queries.append((formula_type, formula_code))
        return {
            "code": formula_code,
            "name": "平滑异同平均线",
            "type": formula_type,
            "params": [{"name": "SHORT", "min": 2.0, "max": 200.0, "default": 12.0}],
            "lines": [{"name": "DIF"}],
            "provider": "tdx",
        }

    async def execute_formula(
        self,
        kind: str,
        formula_name: str,
        formula_arg: str,
        xsflag: int | None,
        timeout_ms: int,
    ) -> dict[str, Any]:
        self.formula_execution_queries.append((kind, formula_name, formula_arg, xsflag, timeout_ms))
        return {
            "kind": kind,
            "formulaName": formula_name,
            "values": {"DIF": [0.0, 0.1]},
            "provider": "tdx",
        }

    async def execute_formula_batch(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.formula_batch_execution_queries.append(
            (kind, payload["formulaName"], payload["stockList"], payload["returnCount"])
        )
        return {
            "kind": kind,
            "formulaName": payload["formulaName"],
            "items": [{"symbol": payload["stockList"][0], "values": {"DIF": [0.1]}}],
            "provider": "tdx",
        }

    async def call_formula(
        self,
        name: str,
        args: dict[str, Any] | list[Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.formula_calls.append((name, args, context))
        return {"name": name, "value": 42}

    async def health(self) -> dict[str, Any]:
        return {"tdxHttpReachable": True, "lastError": None}


class NonDictHealthProvider(FakeTdxProvider):
    async def health(self) -> list[str]:
        return ["not", "a", "dict"]


class RaisingHealthProvider(FakeTdxProvider):
    async def health(self) -> dict[str, Any]:
        raise RuntimeError("tdx health failed")


class FakeAdapter:
    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_called = False

    async def initialize(self) -> None:
        self.initialized = True

    async def shutdown(self) -> None:
        self.shutdown_called = True


class CloseAwareProvider:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class RaisingCloseProvider:
    def __init__(self) -> None:
        self.close_attempted = False

    async def aclose(self) -> None:
        self.close_attempted = True
        raise RuntimeError("provider close failed")


@pytest.fixture
async def v1_client() -> AsyncClient:
    import tdx.main

    previous_provider = tdx.main.tdx_provider
    previous_state_provider = getattr(app.state, "tdx_provider", None)
    tdx.main.tdx_provider = FakeTdxProvider()
    app.state.tdx_provider = tdx.main.tdx_provider
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        tdx.main.tdx_provider = previous_provider
        app.state.tdx_provider = previous_state_provider


def test_v1_provider_lookup_reads_request_app_state() -> None:
    state_app = FastAPI()
    provider = FakeTdxProvider()
    state_app.state.tdx_provider = provider
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/v1/bars/query",
            "headers": [],
            "app": state_app,
        }
    )

    assert tdx_v1_routes._get_provider(request) is provider


@pytest.mark.asyncio
async def test_providers_returns_tdx_provider_envelope(v1_client: AsyncClient) -> None:
    response = await v1_client.get("/providers", headers={"x-request-id": "req-providers"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["requestId"] == "req-providers"
    assert body["provider"] == "tdx"
    assert body["data"]["providers"][0]["id"] == "tdx"


@pytest.mark.asyncio
async def test_providers_returns_tdx_capability_manifest_only(
    v1_client: AsyncClient,
) -> None:
    response = await v1_client.get("/providers")

    assert response.status_code == 200
    body = response.json()
    providers = {provider["id"]: provider for provider in body["data"]["providers"]}

    assert set(providers) == {"tdx"}

    tdx_families = {
        capability["family"]: capability["status"]
        for capability in providers["tdx"]["capabilities"]
    }

    assert tdx_families["bars"] == "supported"
    assert tdx_families["snapshots"] == "supported"
    assert tdx_families["sector-members"] == "supported"
    assert tdx_families["calendar"] == "supported"
    assert tdx_families["securities"] == "supported"
    assert tdx_families["security-info"] == "supported"
    assert tdx_families["sector-list"] == "supported"
    assert tdx_families["price-volume"] == "supported"
    assert tdx_families["security-relations"] == "supported"
    assert tdx_families["ipo-info"] == "supported"
    assert tdx_families["share-capital"] == "supported"
    assert tdx_families["dividend-factors"] == "supported"
    assert tdx_families["convertible-bonds"] == "supported"
    assert tdx_families["etf-info"] == "supported"
    assert tdx_families["financial-data"] == "supported"
    assert tdx_families["single-finance-value"] == "supported"
    assert tdx_families["stock-trade-aggregate"] == "supported"
    assert tdx_families["sector-trade-aggregate"] == "supported"
    assert tdx_families["market-trade-aggregate"] == "supported"
    assert "report-data" not in tdx_families
    assert tdx_families["formula-data"] == "supported"

    tdx_capabilities = {
        capability["family"]: capability for capability in providers["tdx"]["capabilities"]
    }
    assert "get_bars" in tdx_capabilities["bars"]["providerMethods"]
    assert "get_market_data" in tdx_capabilities["bars"]["nativeMethods"]
    assert "get_market_data" not in tdx_capabilities["bars"]["providerMethods"]
    assert "nativeMethods" in tdx_capabilities["raw-diagnostics"]
    assert tdx_families["formula-metadata"] == "supported"
    assert tdx_families["formula-execution"] == "supported"
    assert tdx_families["formula-batch-execution"] == "supported"
    assert tdx_families["formulas"] == "supported"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/v1/bars/query",
            {"provider": "qmt", "symbols": ["600519.SH"], "period": "1d"},
        ),
        (
            "/v1/snapshots/query",
            {"provider": "qmt", "symbols": ["600519.SH"]},
        ),
        (
            "/v1/sectors/query",
            {"provider": "qmt", "sector": "通达信88"},
        ),
        (
            "/v1/formulas/data/set",
            {"provider": "qmt", "stockCode": "688318.SH"},
        ),
    ],
)
@pytest.mark.asyncio
async def test_tdx_v1_rejects_provider_field(
    v1_client: AsyncClient,
    path: str,
    payload: dict[str, Any],
) -> None:
    response = await v1_client.post(path, json=payload)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bars_query_returns_normalized_envelope(v1_client: AsyncClient) -> None:
    response = await v1_client.post(
        "/v1/bars/query",
        json={"symbols": ["600519.SH"], "period": "1m", "count": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["provider"] == "tdx"
    assert body["meta"]["transport"] == "http"
    assert body["data"]["bars"][0]["symbol"] == "600519.SH"
    assert body["data"]["bars"][0]["barTime"] == "2026-04-06T09:31:00+08:00"


@pytest.mark.asyncio
async def test_bars_query_passes_fields_and_adjustment_options(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/bars/query",
        json={
            "symbols": ["600519.SH"],
            "period": "1d",
            "startTime": "2026-04-06T09:30:00",
            "endTime": "2026-04-06T15:00:00",
            "count": 20,
            "fields": ["Open", "Close", "ForwardFactor", "VolInStock"],
            "dividendType": "none",
            "fillData": False,
        },
    )

    assert response.status_code == 200
    assert tdx.main.tdx_provider.bar_queries == [
        {
            "symbols": ["600519.SH"],
            "period": "1d",
            "startTime": "2026-04-06T09:30:00+08:00",
            "endTime": "2026-04-06T15:00:00+08:00",
            "count": 20,
            "fields": ["Open", "Close", "ForwardFactor", "VolInStock"],
            "dividendType": "none",
            "fillData": False,
        }
    ]


@pytest.mark.asyncio
async def test_snapshots_query_returns_normalized_envelope(v1_client: AsyncClient) -> None:
    response = await v1_client.post(
        "/v1/snapshots/query",
        json={"symbols": ["600519.SH"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["provider"] == "tdx"
    assert body["data"]["snapshots"][0]["symbol"] == "600519.SH"
    assert body["data"]["snapshots"][0]["lastClose"] == 9.6


@pytest.mark.asyncio
async def test_raw_call_proxies_method_and_params(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/raw/tdx/call",
        json={"method": "get_market_data", "params": {"stock_list": ["SH600519"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["result"] == {
        "method": "get_market_data",
        "params": {"stock_list": ["SH600519"]},
    }
    assert tdx.main.tdx_provider.raw_calls == [("get_market_data", {"stock_list": ["SH600519"]})]


@pytest.mark.asyncio
async def test_sectors_query_returns_symbols(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post("/v1/sectors/query", json={"sector": "通达信88"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["symbols"] == ["600519.SH", "000001.SZ"]
    assert tdx.main.tdx_provider.sector_queries == ["通达信88"]


@pytest.mark.asyncio
async def test_sector_list_query_returns_normalized_sectors(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post("/v1/sectors/list/query", json={"listType": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["sectors"][0]["code"] == "880081.SH"
    assert tdx.main.tdx_provider.sector_list_queries == [1]


@pytest.mark.asyncio
async def test_calendar_query_returns_trading_dates(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/calendar/trading-dates/query",
        json={"market": "SH", "count": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["tradingDates"] == ["2026-06-25", "2026-06-26"]
    assert tdx.main.tdx_provider.trading_date_queries == [("SH", None, None, 2)]


@pytest.mark.asyncio
async def test_securities_query_returns_normalized_symbols(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post("/v1/securities/query", json={"market": "5"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["securities"][0]["symbol"] == "600519.SH"
    assert tdx.main.tdx_provider.security_list_queries == ["5"]


@pytest.mark.asyncio
async def test_security_info_query_returns_normalized_metadata(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/securities/info/query",
        json={"symbols": ["600519.SH"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["securities"][0]["name"] == "贵州茅台"
    assert tdx.main.tdx_provider.security_info_queries == [["600519.SH"]]


@pytest.mark.asyncio
async def test_price_volume_query_returns_normalized_items(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/price-volume/query",
        json={"symbols": ["600519.SH"], "fields": ["price", "volume"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["price"] == 1168.63
    assert tdx.main.tdx_provider.price_volume_queries == [(["600519.SH"], ["price", "volume"])]


@pytest.mark.asyncio
async def test_reference_relations_query_returns_normalized_relations(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reference/relations/query",
        json={"symbol": "600519.SH"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["relations"][0]["category"] == "industry"
    assert tdx.main.tdx_provider.relation_queries == ["600519.SH"]


@pytest.mark.asyncio
async def test_reference_ipo_query_returns_normalized_items(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reference/ipo/query",
        json={"ipoType": 2, "ipoDate": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["subscribeCode"] == "371036"
    assert tdx.main.tdx_provider.ipo_queries == [(2, 1)]


@pytest.mark.asyncio
async def test_reference_share_capital_query_uses_date_list(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reference/share-capital/query",
        json={"symbol": "600519.SH", "dateList": ["20250101"], "count": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["totalShareCapital"] == 182942480.0
    assert tdx.main.tdx_provider.share_capital_queries == [("600519.SH", ["20250101"], 1)]


@pytest.mark.asyncio
async def test_reference_share_capital_query_uses_date_range(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reference/share-capital/query",
        json={"symbol": "600519.SH", "startDate": "20250101", "endDate": "20250601"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert tdx.main.tdx_provider.share_capital_by_date_queries == [
        ("600519.SH", "20250101", "20250601")
    ]


@pytest.mark.asyncio
async def test_reference_dividend_factors_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reference/dividend-factors/query",
        json={"symbol": "600519.SH", "startTime": "20250101", "endTime": "20251231"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["bonus"] == 1.23
    assert tdx.main.tdx_provider.dividend_factor_queries == [("600519.SH", "20250101", "20251231")]


@pytest.mark.asyncio
async def test_instruments_convertible_bonds_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/instruments/convertible-bonds/query",
        json={
            "symbol": "123039.SZ",
            "fields": ["KZZCode", "HSCode"],
            "nativeMethod": "get_kzz_info",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["bondCode"] == "123039.SZ"
    assert tdx.main.tdx_provider.convertible_bond_queries == [
        ("123039.SZ", ["KZZCode", "HSCode"], "get_kzz_info")
    ]


@pytest.mark.asyncio
async def test_instruments_tracking_etfs_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/instruments/tracking-etfs/query",
        json={"indexSymbol": "950162.CSI"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["indexSymbol"] == "950162.CSI"
    assert tdx.main.tdx_provider.track_etf_queries == ["950162.CSI"]


@pytest.mark.asyncio
async def test_financial_data_query_returns_normalized_items(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/finance/financial-data/query",
        json={
            "symbols": ["600519.SH"],
            "fields": ["FN193"],
            "startTime": "20250101",
            "endTime": "20251231",
            "reportType": "tag_time",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["symbol"] == "600519.SH"
    assert body["data"]["items"][0]["field"] == "FN193"
    assert body["data"]["items"][0]["value"] == 162.47
    assert tdx.main.tdx_provider.financial_data_queries == [
        (["600519.SH"], ["FN193"], "20250101", "20251231", "tag_time")
    ]


@pytest.mark.asyncio
async def test_financial_data_by_date_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/finance/financial-data/by-date/query",
        json={"symbols": ["600519.SH"], "fields": ["FN194"], "year": 0, "mmdd": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["field"] == "FN194"
    assert body["data"]["items"][0]["value"] == 69.67
    assert tdx.main.tdx_provider.financial_data_by_date_queries == [
        (["600519.SH"], ["FN194"], 0, 0)
    ]


@pytest.mark.asyncio
async def test_single_finance_data_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/finance/single-data/query",
        json={"symbols": ["688318.SH"], "fields": ["GO1"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["field"] == "GO1"
    assert body["data"]["items"][0]["value"] == 107.41
    assert tdx.main.tdx_provider.single_finance_value_queries == [(["688318.SH"], ["GO1"])]


@pytest.mark.asyncio
async def test_stock_trade_aggregate_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reports/stock-trade/query",
        json={
            "symbols": ["688318.SH"],
            "fields": ["GP3"],
            "startTime": "20250101",
            "endTime": "20250102",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["scope"] == "stock"
    assert body["data"]["items"][0]["values"] == [141405.89, 11113.0]
    assert tdx.main.tdx_provider.stock_trade_aggregate_queries == [
        (["688318.SH"], ["GP3"], "20250101", "20250102")
    ]


@pytest.mark.asyncio
async def test_stock_trade_aggregate_by_date_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reports/stock-trade/by-date/query",
        json={"symbols": ["688318.SH"], "fields": ["GP1"], "year": 0, "mmdd": 0},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["values"] == [24154.0, 0.0]
    assert tdx.main.tdx_provider.stock_trade_aggregate_by_date_queries == [
        (["688318.SH"], ["GP1"], 0, 0)
    ]


@pytest.mark.asyncio
async def test_sector_trade_aggregate_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reports/sector-trade/query",
        json={
            "sectorCodes": ["880660.SH"],
            "fields": ["BK5"],
            "startTime": "20250101",
            "endTime": "20250102",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["scope"] == "sector"
    assert tdx.main.tdx_provider.sector_trade_aggregate_queries == [
        (["880660.SH"], ["BK5"], "20250101", "20250102")
    ]


@pytest.mark.asyncio
async def test_sector_trade_aggregate_by_date_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reports/sector-trade/by-date/query",
        json={"sectorCodes": ["880660.SH"], "fields": ["BK9"], "year": 0, "mmdd": 0},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["values"] == [3.0, 31.0]
    assert tdx.main.tdx_provider.sector_trade_aggregate_by_date_queries == [
        (["880660.SH"], ["BK9"], 0, 0)
    ]


@pytest.mark.asyncio
async def test_market_trade_aggregate_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reports/market-trade/query",
        json={"fields": ["SC1"], "startTime": "20250101", "endTime": "20250102"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["scope"] == "market"
    assert tdx.main.tdx_provider.market_trade_aggregate_queries == [
        (["SC1"], "20250101", "20250102")
    ]


@pytest.mark.asyncio
async def test_market_trade_aggregate_by_date_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/reports/market-trade/by-date/query",
        json={"fields": ["SC10"], "year": 0, "mmdd": 0},
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["values"] == [0.0, 181415.13]
    assert tdx.main.tdx_provider.market_trade_aggregate_by_date_queries == [(["SC10"], 0, 0)]


@pytest.mark.asyncio
async def test_report_data_query_route_is_not_exposed(v1_client: AsyncClient) -> None:
    response = await v1_client.post(
        "/v1/reports/data/query",
        json={"symbol": "600519.SH"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_report_data_query_is_absent_from_openapi(v1_client: AsyncClient) -> None:
    response = await v1_client.get("/openapi.json")

    assert response.status_code == 200
    assert "/v1/reports/data/query" not in response.json()["paths"]


@pytest.mark.asyncio
async def test_formula_format_data_query_returns_normalized_items(
    v1_client: AsyncClient,
) -> None:
    import tdx.main

    payload = {"data": {"688318.SH": [{"Close": 144.4}]}}
    response = await v1_client.post("/v1/formulas/data/format/query", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["symbol"] == "688318.SH"
    assert tdx.main.tdx_provider.formula_format_queries == [payload["data"]]


@pytest.mark.asyncio
async def test_formula_set_data_returns_result(v1_client: AsyncClient) -> None:
    import tdx.main

    payload = {
        "stockCode": "688318.SH",
        "stockPeriod": "1d",
        "stockData": [{"Close": 144.4}],
        "count": 1,
        "dividendType": 1,
    }
    response = await v1_client.post("/v1/formulas/data/set", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["result"]["runId"] == "1"
    assert tdx.main.tdx_provider.formula_set_data_queries == [
        {
            "stockCode": "688318.SH",
            "stockPeriod": "1d",
            "stockData": [{"Close": 144.4}],
            "count": 1,
            "dividendType": 1,
            "timeoutMs": 10000,
        }
    ]


@pytest.mark.asyncio
async def test_formula_set_data_info_returns_result(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/formulas/data/set-info",
        json={"stockCode": "688318.SH", "stockPeriod": "1d", "count": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["result"]["runId"] == "2"
    assert tdx.main.tdx_provider.formula_set_data_info_queries[0]["stockCode"] == "688318.SH"


@pytest.mark.asyncio
async def test_formula_get_data_returns_item(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post("/v1/formulas/data/query", json={})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["item"]["symbol"] == "688318.SH"
    assert tdx.main.tdx_provider.formula_get_data_calls == 1


@pytest.mark.asyncio
async def test_formula_metadata_query_returns_items(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/formulas/metadata/query",
        json={"formulaType": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["items"][0]["code"] == "MA"
    assert tdx.main.tdx_provider.formula_get_all_queries == [0]


@pytest.mark.asyncio
async def test_formula_metadata_info_query_returns_item(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/formulas/metadata/info/query",
        json={"formulaType": 0, "formulaCode": "MACD"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["item"]["params"][0]["name"] == "SHORT"
    assert tdx.main.tdx_provider.formula_get_info_queries == [(0, "MACD")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "kind", "xsflag"),
    [
        ("/v1/formulas/zb/execute", "zb", 8),
        ("/v1/formulas/xg/execute", "xg", None),
        ("/v1/formulas/exp/execute", "exp", None),
    ],
)
async def test_formula_execution_returns_result(
    v1_client: AsyncClient,
    path: str,
    kind: str,
    xsflag: int | None,
) -> None:
    import tdx.main

    payload: dict[str, Any] = {
        "formulaName": "MACD",
        "formulaArg": "12,26,9",
        "timeoutMs": 5000,
    }
    if xsflag is not None:
        payload["xsflag"] = xsflag

    response = await v1_client.post(path, json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["result"]["kind"] == kind
    assert tdx.main.tdx_provider.formula_execution_queries[-1] == (
        kind,
        "MACD",
        "12,26,9",
        xsflag,
        5000,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/v1/formulas/batch/xg/execute", "xg"),
        ("/v1/formulas/batch/zb/execute", "zb"),
        ("/v1/formulas/batch/exp/execute", "exp"),
    ],
)
async def test_formula_batch_execution_returns_result(
    v1_client: AsyncClient,
    path: str,
    kind: str,
) -> None:
    import tdx.main

    response = await v1_client.post(
        path,
        json={
            "formulaName": "UPN",
            "formulaArg": "3",
            "stockList": ["688318.SH"],
            "returnCount": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["result"]["kind"] == kind
    assert tdx.main.tdx_provider.formula_batch_execution_queries[-1] == (
        kind,
        "UPN",
        ["688318.SH"],
        1,
    )


@pytest.mark.asyncio
async def test_formula_batch_execution_rejects_oversized_stock_list(
    v1_client: AsyncClient,
) -> None:
    response = await v1_client.post(
        "/v1/formulas/batch/xg/execute",
        json={
            "formulaName": "UPN",
            "stockList": [f"{index:06d}.SH" for index in range(201)],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error"]["code"] == "FORMULA_REQUEST_LIMIT_EXCEEDED"
    assert body["error"]["details"]["limit"] == "stockList"


@pytest.mark.asyncio
async def test_formulas_call_returns_result(v1_client: AsyncClient) -> None:
    import tdx.main

    response = await v1_client.post(
        "/v1/formulas/call",
        json={"name": "MY_FORMULA", "args": {"symbol": "600519.SH"}, "context": {"period": "1d"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["result"] == {"name": "MY_FORMULA", "value": 42}
    assert tdx.main.tdx_provider.formula_calls == [
        ("MY_FORMULA", {"symbol": "600519.SH"}, {"period": "1d"})
    ]


@pytest.mark.asyncio
async def test_provider_error_returns_failure_envelope(v1_client: AsyncClient) -> None:
    import tdx.main

    tdx.main.tdx_provider.fail_bars = True
    response = await v1_client.post(
        "/v1/bars/query",
        json={"symbols": ["600519.SH"], "period": "1m", "count": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["provider"] == "tdx"
    assert body["data"] is None
    assert body["error"] == {
        "code": "TDX_HTTP_UNAVAILABLE",
        "message": "TDX HTTP is unavailable",
        "retryable": True,
        "details": {"method": "get_market_data"},
    }


@pytest.mark.asyncio
async def test_health_includes_enriched_tdx_state(v1_client: AsyncClient) -> None:
    response = await v1_client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["instance"] == "tdx"
    assert "connections" in body
    assert body["tdxHttpReachable"] is True
    assert body["wsConnected"] is False
    assert body["tdxExperimentalBridgeReady"] is False


@pytest.mark.asyncio
async def test_public_experimental_health_route_does_not_exist(
    v1_client: AsyncClient,
) -> None:
    response = await v1_client.get("/health/experimental")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_health_handles_non_dict_provider_health() -> None:
    import tdx.main

    previous_provider = tdx.main.tdx_provider
    tdx.main.tdx_provider = NonDictHealthProvider()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        assert response.json()["tdxHttpReachable"] is False
    finally:
        tdx.main.tdx_provider = previous_provider


@pytest.mark.asyncio
async def test_health_surfaces_provider_health_exceptions() -> None:
    import tdx.main

    previous_provider = tdx.main.tdx_provider
    tdx.main.tdx_provider = RaisingHealthProvider()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["tdxHttpReachable"] is False
        assert body["lastError"] == "tdx health failed"
    finally:
        tdx.main.tdx_provider = previous_provider


@pytest.mark.asyncio
async def test_lifespan_creates_and_closes_http_provider(monkeypatch) -> None:
    import tdx.main

    previous_provider = tdx.main.tdx_provider
    previous_owned_provider = tdx.main._tdx_provider_owned_by_main
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", CloseAwareProvider)
    tdx.main.tdx_provider = None

    try:
        async with tdx.main.lifespan(app):
            assert isinstance(tdx.main.tdx_provider, CloseAwareProvider)
        assert tdx.main.tdx_provider is None
    finally:
        tdx.main.tdx_provider = previous_provider
        tdx.main._tdx_provider_owned_by_main = previous_owned_provider


@pytest.mark.asyncio
async def test_lifespan_closes_owned_provider_not_replacement(monkeypatch) -> None:
    import tdx.main

    previous_provider = tdx.main.tdx_provider
    previous_owned_provider = tdx.main._tdx_provider_owned_by_main
    owned_provider = CloseAwareProvider()
    replacement_provider = CloseAwareProvider()
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: owned_provider)
    tdx.main.tdx_provider = None

    try:
        async with tdx.main.lifespan(app):
            assert tdx.main.tdx_provider is owned_provider
            tdx.main.tdx_provider = replacement_provider

        assert owned_provider.closed is True
        assert replacement_provider.closed is False
        assert tdx.main.tdx_provider is replacement_provider
    finally:
        tdx.main.tdx_provider = previous_provider
        tdx.main._tdx_provider_owned_by_main = previous_owned_provider


@pytest.mark.asyncio
async def test_lifespan_clears_owned_provider_when_close_raises(monkeypatch) -> None:
    import tdx.main

    previous_provider = tdx.main.tdx_provider
    previous_owned_provider = tdx.main._tdx_provider_owned_by_main
    owned_provider = RaisingCloseProvider()
    monkeypatch.setattr(tdx.main, "TdxDatasourceProvider", lambda: owned_provider)
    tdx.main.tdx_provider = None

    try:
        with pytest.raises(RuntimeError, match="provider close failed"):
            async with tdx.main.lifespan(app):
                assert tdx.main.tdx_provider is owned_provider

        assert owned_provider.close_attempted is True
        assert tdx.main.tdx_provider is None
        assert tdx.main._tdx_provider_owned_by_main is None
    finally:
        tdx.main.tdx_provider = previous_provider
        tdx.main._tdx_provider_owned_by_main = previous_owned_provider
