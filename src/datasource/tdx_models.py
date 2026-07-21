from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.config import settings
from src.datasource.contracts import normalize_beijing_iso


class TdxModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


def _formula_timeout_ms() -> int:
    return settings.tdx.formula_timeout_ms


def _empty_stock_data() -> list[dict[str, Any]]:
    return []


class TdxBar(TdxModel):
    symbol: str
    period: str
    bar_time: str = Field(alias="barTime")
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    forward_factor: float | None = Field(default=None, alias="forwardFactor")
    vol_in_stock: float | None = Field(default=None, alias="volInStock")
    provider: str = "tdx"
    received_at: str = Field(alias="receivedAt")

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("exclude_none", True)
        return super().model_dump(*args, **kwargs)

    @property
    def barTime(self) -> str:
        return self.bar_time

    @property
    def forwardFactor(self) -> float | None:
        return self.forward_factor

    @property
    def volInStock(self) -> float | None:
        return self.vol_in_stock

    @property
    def receivedAt(self) -> str:
        return self.received_at

    @field_validator("bar_time", "received_at", mode="before")
    @classmethod
    def normalize_time_fields(cls, value: str) -> str:
        normalized = normalize_beijing_iso(value)
        if normalized is None:
            msg = "barTime and receivedAt are required"
            raise ValueError(msg)
        return normalized


class TdxSnapshot(TdxModel):
    symbol: str
    last: float
    open: float
    high: float
    low: float
    last_close: float = Field(alias="lastClose")
    volume: float
    amount: float
    provider: str = "tdx"
    as_of: str = Field(alias="asOf")

    @property
    def lastClose(self) -> float:
        return self.last_close

    @property
    def asOf(self) -> str:
        return self.as_of

    @field_validator("as_of", mode="before")
    @classmethod
    def normalize_as_of(cls, value: str) -> str:
        normalized = normalize_beijing_iso(value)
        if normalized is None:
            msg = "asOf is required"
            raise ValueError(msg)
        return normalized


class TdxBarQueryRequest(TdxModel):
    symbols: list[str]
    period: str
    start_time: str | None = Field(default=None, alias="startTime")
    end_time: str | None = Field(default=None, alias="endTime")
    count: int | None = None
    fields: list[str] | None = None
    dividend_type: Literal["none", "front", "back"] = Field(default="front", alias="dividendType")
    fill_data: bool = Field(default=True, alias="fillData")
    include_raw: bool = Field(default=False, alias="includeRaw")

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def normalize_time_filters(cls, value: str | None) -> str | None:
        return normalize_beijing_iso(value)


class TdxSnapshotQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str] | None = None
    include_raw: bool = Field(default=False, alias="includeRaw")


class TdxPriceVolumeQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str] | None = None
    include_raw: bool = Field(default=False, alias="includeRaw")


class TdxTradingDatesQueryRequest(TdxModel):
    market: str = "SH"
    start_time: str | None = Field(default=None, alias="startTime")
    end_time: str | None = Field(default=None, alias="endTime")
    count: int | None = None


class TdxSecuritiesQueryRequest(TdxModel):
    market: str = "5"


class TdxSecurityInfoQueryRequest(TdxModel):
    symbols: list[str]
    include_raw: bool = Field(default=True, alias="includeRaw")


class TdxSectorListQueryRequest(TdxModel):
    list_type: int = Field(default=0, alias="listType")


class TdxSecurityRelationsQueryRequest(TdxModel):
    symbol: str


class TdxIpoInfoQueryRequest(TdxModel):
    ipo_type: int = Field(default=0, alias="ipoType")
    ipo_date: int = Field(default=0, alias="ipoDate")


class TdxShareCapitalQueryRequest(TdxModel):
    symbol: str
    date_list: list[str] = Field(default_factory=list, alias="dateList")
    count: int = 1
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")


class TdxDividendFactorsQueryRequest(TdxModel):
    symbol: str
    start_time: str | None = Field(default=None, alias="startTime")
    end_time: str | None = Field(default=None, alias="endTime")


class TdxConvertibleBondInfoQueryRequest(TdxModel):
    symbol: str
    fields: list[str] | None = None
    native_method: Literal["get_kzz_info", "get_cb_info"] = Field(
        default="get_kzz_info",
        alias="nativeMethod",
    )


class TdxTrackingEtfsQueryRequest(TdxModel):
    index_symbol: str = Field(alias="indexSymbol")


class TdxFinancialDataQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str]
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")
    report_type: str = Field(default="report_time", alias="reportType")


class TdxFinancialDataByDateQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str]
    year: int = 0
    mmdd: int = 0


class TdxSingleFinanceValueQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str]


class TdxStockTradeAggregateQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str]
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")


class TdxStockTradeAggregateByDateQueryRequest(TdxModel):
    symbols: list[str]
    fields: list[str]
    year: int = 0
    mmdd: int = 0


class TdxSectorTradeAggregateQueryRequest(TdxModel):
    sector_codes: list[str] = Field(alias="sectorCodes")
    fields: list[str]
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")


class TdxSectorTradeAggregateByDateQueryRequest(TdxModel):
    sector_codes: list[str] = Field(alias="sectorCodes")
    fields: list[str]
    year: int = 0
    mmdd: int = 0


class TdxMarketTradeAggregateQueryRequest(TdxModel):
    fields: list[str]
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")


class TdxMarketTradeAggregateByDateQueryRequest(TdxModel):
    fields: list[str]
    year: int = 0
    mmdd: int = 0


class TdxFormulaFormatDataRequest(TdxModel):
    data: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaSetDataRequest(TdxModel):
    stock_code: str = Field(alias="stockCode")
    stock_period: str = Field(default="1d", alias="stockPeriod")
    stock_data: list[dict[str, Any]] = Field(default_factory=_empty_stock_data, alias="stockData")
    count: int = -1
    dividend_type: int = Field(default=0, alias="dividendType")
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaSetDataInfoRequest(TdxModel):
    stock_code: str = Field(alias="stockCode")
    stock_period: str = Field(default="1d", alias="stockPeriod")
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")
    count: int = -1
    dividend_type: int = Field(default=0, alias="dividendType")
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaGetDataRequest(TdxModel):
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaMetadataQueryRequest(TdxModel):
    formula_type: int = Field(default=0, alias="formulaType")
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaMetadataInfoQueryRequest(TdxModel):
    formula_type: int = Field(default=0, alias="formulaType")
    formula_code: str = Field(alias="formulaCode")
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaExecutionRequest(TdxModel):
    formula_name: str = Field(alias="formulaName")
    formula_arg: str = Field(default="", alias="formulaArg")
    xsflag: int | None = None
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaBatchExecutionRequest(TdxModel):
    formula_name: str = Field(alias="formulaName")
    formula_arg: str = Field(default="", alias="formulaArg")
    xsflag: int | None = None
    return_count: int = Field(default=1, alias="returnCount")
    return_date: bool = Field(default=False, alias="returnDate")
    stock_list: list[str] = Field(default_factory=list, alias="stockList")
    stock_period: str = Field(default="1d", alias="stockPeriod")
    start_time: str = Field(default="", alias="startTime")
    end_time: str = Field(default="", alias="endTime")
    count: int = -1
    dividend_type: int = Field(default=0, alias="dividendType")
    timeout_ms: int = Field(default_factory=_formula_timeout_ms, alias="timeoutMs")


class TdxFormulaOperationResult(TdxModel):
    ok: bool
    message: str
    provider: str = "tdx"
    raw: Any | None = None


class RawTdxCallRequest(TdxModel):
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
