# TDX OpenAPI Summary (builtin)

Title: Mist DataSource - TDX
Version: 1.0.0

Generated from the `tdx` FastAPI app in `builtin` mode.

## GET /health

- Operation ID: `health_health_get`
- Tags: -
- Summary: Health
- Request Body: `-`
- Parameters: -
- Responses: 200: TdxDatasourceHealth

## GET /providers

- Operation ID: `providers_providers_get`
- Tags: V1
- Summary: Providers
- Request Body: `-`
- Parameters: -
- Responses: 200: -

## GET /tdx/bridge/evidence/{symbol}

- Operation ID: `bridge_native_evidence_tdx_bridge_evidence__symbol__get`
- Tags: TDX Bridge
- Summary: Bridge Native Evidence
- Request Body: `-`
- Parameters: symbol (path, string, required=true)
- Responses: 200: object; 422: HTTPValidationError

## GET /tdx/bridge/health

- Operation ID: `bridge_health_tdx_bridge_health_get`
- Tags: TDX Bridge
- Summary: Bridge Health
- Request Body: `-`
- Parameters: -
- Responses: 200: TdxBridgeHealth

## POST /tdx/bridge/observability

- Operation ID: `post_observability_tdx_bridge_observability_post`
- Tags: TDX Bridge
- Summary: Post Observability
- Request Body: `ObservabilityRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/owner

- Operation ID: `register_owner_tdx_bridge_owner_post`
- Tags: TDX Bridge
- Summary: Register Owner
- Request Body: `OwnerRegisterRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/poll

- Operation ID: `poll_tdx_bridge_poll_post`
- Tags: TDX Bridge
- Summary: Poll
- Request Body: `PollRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/result

- Operation ID: `post_result_tdx_bridge_result_post`
- Tags: TDX Bridge
- Summary: Post Result
- Request Body: `ResultRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/snapshot

- Operation ID: `post_snapshot_tdx_bridge_snapshot_post`
- Tags: TDX Bridge
- Summary: Post Snapshot
- Request Body: `SnapshotRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /v1/bars/query

- Operation ID: `query_bars_v1_bars_query_post`
- Tags: V1
- Summary: Query Bars
- Request Body: `TdxBarQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/calendar/trading-dates/query

- Operation ID: `query_trading_dates_v1_calendar_trading_dates_query_post`
- Tags: V1
- Summary: Query Trading Dates
- Request Body: `TdxTradingDatesQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/finance/financial-data/by-date/query

- Operation ID: `query_financial_data_by_date_v1_finance_financial_data_by_date_query_post`
- Tags: V1
- Summary: Query Financial Data By Date
- Request Body: `TdxFinancialDataByDateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/finance/financial-data/query

- Operation ID: `query_financial_data_v1_finance_financial_data_query_post`
- Tags: V1
- Summary: Query Financial Data
- Request Body: `TdxFinancialDataQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/finance/single-data/query

- Operation ID: `query_single_finance_data_v1_finance_single_data_query_post`
- Tags: V1
- Summary: Query Single Finance Data
- Request Body: `TdxSingleFinanceValueQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/batch/exp/execute

- Operation ID: `execute_formula_batch_exp_v1_formulas_batch_exp_execute_post`
- Tags: V1
- Summary: Execute Formula Batch Exp
- Request Body: `TdxFormulaBatchExecutionRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/batch/xg/execute

- Operation ID: `execute_formula_batch_xg_v1_formulas_batch_xg_execute_post`
- Tags: V1
- Summary: Execute Formula Batch Xg
- Request Body: `TdxFormulaBatchExecutionRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/batch/zb/execute

- Operation ID: `execute_formula_batch_zb_v1_formulas_batch_zb_execute_post`
- Tags: V1
- Summary: Execute Formula Batch Zb
- Request Body: `TdxFormulaBatchExecutionRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/call

- Operation ID: `call_formula_v1_formulas_call_post`
- Tags: V1
- Summary: Call Formula
- Request Body: `FormulaCallRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/data/format/query

- Operation ID: `query_formula_format_data_v1_formulas_data_format_query_post`
- Tags: V1
- Summary: Query Formula Format Data
- Request Body: `TdxFormulaFormatDataRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/data/query

- Operation ID: `query_formula_data_v1_formulas_data_query_post`
- Tags: V1
- Summary: Query Formula Data
- Request Body: `TdxFormulaGetDataRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/data/set

- Operation ID: `set_formula_data_v1_formulas_data_set_post`
- Tags: V1
- Summary: Set Formula Data
- Request Body: `TdxFormulaSetDataRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/data/set-info

- Operation ID: `set_formula_data_info_v1_formulas_data_set_info_post`
- Tags: V1
- Summary: Set Formula Data Info
- Request Body: `TdxFormulaSetDataInfoRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/exp/execute

- Operation ID: `execute_formula_exp_v1_formulas_exp_execute_post`
- Tags: V1
- Summary: Execute Formula Exp
- Request Body: `TdxFormulaExecutionRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/metadata/info/query

- Operation ID: `query_formula_metadata_info_v1_formulas_metadata_info_query_post`
- Tags: V1
- Summary: Query Formula Metadata Info
- Request Body: `TdxFormulaMetadataInfoQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/metadata/query

- Operation ID: `query_formula_metadata_v1_formulas_metadata_query_post`
- Tags: V1
- Summary: Query Formula Metadata
- Request Body: `TdxFormulaMetadataQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/xg/execute

- Operation ID: `execute_formula_xg_v1_formulas_xg_execute_post`
- Tags: V1
- Summary: Execute Formula Xg
- Request Body: `TdxFormulaExecutionRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/formulas/zb/execute

- Operation ID: `execute_formula_zb_v1_formulas_zb_execute_post`
- Tags: V1
- Summary: Execute Formula Zb
- Request Body: `TdxFormulaExecutionRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/instruments/convertible-bonds/query

- Operation ID: `query_convertible_bonds_v1_instruments_convertible_bonds_query_post`
- Tags: V1
- Summary: Query Convertible Bonds
- Request Body: `TdxConvertibleBondInfoQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/instruments/tracking-etfs/query

- Operation ID: `query_tracking_etfs_v1_instruments_tracking_etfs_query_post`
- Tags: V1
- Summary: Query Tracking Etfs
- Request Body: `TdxTrackingEtfsQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/price-volume/query

- Operation ID: `query_price_volume_v1_price_volume_query_post`
- Tags: V1
- Summary: Query Price Volume
- Request Body: `TdxPriceVolumeQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/raw/tdx/call

- Operation ID: `raw_tdx_call_v1_raw_tdx_call_post`
- Tags: V1
- Summary: Raw Tdx Call
- Request Body: `RawTdxCallRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reference/dividend-factors/query

- Operation ID: `query_dividend_factors_v1_reference_dividend_factors_query_post`
- Tags: V1
- Summary: Query Dividend Factors
- Request Body: `TdxDividendFactorsQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reference/ipo/query

- Operation ID: `query_ipo_info_v1_reference_ipo_query_post`
- Tags: V1
- Summary: Query Ipo Info
- Request Body: `TdxIpoInfoQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reference/relations/query

- Operation ID: `query_security_relations_v1_reference_relations_query_post`
- Tags: V1
- Summary: Query Security Relations
- Request Body: `TdxSecurityRelationsQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reference/share-capital/query

- Operation ID: `query_share_capital_v1_reference_share_capital_query_post`
- Tags: V1
- Summary: Query Share Capital
- Request Body: `TdxShareCapitalQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reports/market-trade/by-date/query

- Operation ID: `query_market_trade_aggregate_by_date_v1_reports_market_trade_by_date_query_post`
- Tags: V1
- Summary: Query Market Trade Aggregate By Date
- Request Body: `TdxMarketTradeAggregateByDateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reports/market-trade/query

- Operation ID: `query_market_trade_aggregate_v1_reports_market_trade_query_post`
- Tags: V1
- Summary: Query Market Trade Aggregate
- Request Body: `TdxMarketTradeAggregateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reports/sector-trade/by-date/query

- Operation ID: `query_sector_trade_aggregate_by_date_v1_reports_sector_trade_by_date_query_post`
- Tags: V1
- Summary: Query Sector Trade Aggregate By Date
- Request Body: `TdxSectorTradeAggregateByDateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reports/sector-trade/query

- Operation ID: `query_sector_trade_aggregate_v1_reports_sector_trade_query_post`
- Tags: V1
- Summary: Query Sector Trade Aggregate
- Request Body: `TdxSectorTradeAggregateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reports/stock-trade/by-date/query

- Operation ID: `query_stock_trade_aggregate_by_date_v1_reports_stock_trade_by_date_query_post`
- Tags: V1
- Summary: Query Stock Trade Aggregate By Date
- Request Body: `TdxStockTradeAggregateByDateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/reports/stock-trade/query

- Operation ID: `query_stock_trade_aggregate_v1_reports_stock_trade_query_post`
- Tags: V1
- Summary: Query Stock Trade Aggregate
- Request Body: `TdxStockTradeAggregateQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/sectors/list/query

- Operation ID: `query_sector_list_v1_sectors_list_query_post`
- Tags: V1
- Summary: Query Sector List
- Request Body: `TdxSectorListQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/sectors/query

- Operation ID: `query_sectors_v1_sectors_query_post`
- Tags: V1
- Summary: Query Sectors
- Request Body: `SectorQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/securities/info/query

- Operation ID: `query_security_info_v1_securities_info_query_post`
- Tags: V1
- Summary: Query Security Info
- Request Body: `TdxSecurityInfoQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /v1/securities/query

- Operation ID: `query_securities_v1_securities_query_post`
- Tags: V1
- Summary: Query Securities
- Request Body: `TdxSecuritiesQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## Schemas

- `FormulaCallRequest`
- `HTTPValidationError`
- `ObservabilityRequest`
- `OwnerRegisterRequest`
- `PollRequest`
- `RawTdxCallRequest`
- `RejectedItem`
- `ResultRequest`
- `SectorQueryRequest`
- `SnapshotRequest`
- `TdxBarQueryRequest`
- `TdxBridgeHealth`
- `TdxConvertibleBondInfoQueryRequest`
- `TdxDatasourceHealth`
- `TdxDividendFactorsQueryRequest`
- `TdxFinancialDataByDateQueryRequest`
- `TdxFinancialDataQueryRequest`
- `TdxFormulaBatchExecutionRequest`
- `TdxFormulaExecutionRequest`
- `TdxFormulaFormatDataRequest`
- `TdxFormulaGetDataRequest`
- `TdxFormulaMetadataInfoQueryRequest`
- `TdxFormulaMetadataQueryRequest`
- `TdxFormulaSetDataInfoRequest`
- `TdxFormulaSetDataRequest`
- `TdxIpoInfoQueryRequest`
- `TdxMarketTradeAggregateByDateQueryRequest`
- `TdxMarketTradeAggregateQueryRequest`
- `TdxPriceVolumeQueryRequest`
- `TdxSectorListQueryRequest`
- `TdxSectorTradeAggregateByDateQueryRequest`
- `TdxSectorTradeAggregateQueryRequest`
- `TdxSecuritiesQueryRequest`
- `TdxSecurityInfoQueryRequest`
- `TdxSecurityRelationsQueryRequest`
- `TdxShareCapitalQueryRequest`
- `TdxSingleFinanceValueQueryRequest`
- `TdxStockTradeAggregateByDateQueryRequest`
- `TdxStockTradeAggregateQueryRequest`
- `TdxTrackingEtfsQueryRequest`
- `TdxTradingDatesQueryRequest`
- `ValidationError`
