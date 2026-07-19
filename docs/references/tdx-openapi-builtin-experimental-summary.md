# TDX OpenAPI Summary (builtin_experimental)

Title: Mist DataSource - TDX Adapter
Version: 0.1.0

Generated from the `tdx` FastAPI app in `builtin_experimental` mode.

## GET /api/tdx/bkjy-value

- Operation ID: `get_bkjy_value_api_tdx_bkjy_value_get`
- Tags: Value
- Summary: Get Bkjy Value
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true); start_time (query, string, required=false); end_time (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/bkjy-value-by-date

- Operation ID: `get_bkjy_value_by_date_api_tdx_bkjy_value_by_date_get`
- Tags: Value
- Summary: Get Bkjy Value By Date
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true); year (query, integer, required=true); mmdd (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/clear-sector

- Operation ID: `clear_sector_api_tdx_clear_sector_post`
- Tags: Sector
- Summary: Clear Sector
- Request Body: `SectorRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/create-sector

- Operation ID: `create_sector_api_tdx_create_sector_post`
- Tags: Sector
- Summary: Create Sector
- Request Body: `SectorRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/delete-sector

- Operation ID: `delete_sector_api_tdx_delete_sector_post`
- Tags: Sector
- Summary: Delete Sector
- Request Body: `SectorRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/divid-factors

- Operation ID: `get_divid_factors_api_tdx_divid_factors_get`
- Tags: Market
- Summary: Get Divid Factors
- Request Body: `-`
- Parameters: stock_code (query, string, required=true); start_time (query, string, required=false); end_time (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/download-file

- Operation ID: `download_file_api_tdx_download_file_post`
- Tags: Market
- Summary: Download File
- Request Body: `-`
- Parameters: stock_code (query, string, required=false); down_time (query, string, required=false); down_type (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/exec-to-tdx

- Operation ID: `exec_to_tdx_api_tdx_exec_to_tdx_post`
- Tags: Client
- Summary: Exec To Tdx
- Request Body: `ExecRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/financial-data

- Operation ID: `get_financial_data_api_tdx_financial_data_get`
- Tags: Financial
- Summary: Get Financial Data
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true); start_time (query, string, required=false); end_time (query, string, required=false); report_type (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/financial-data-by-date

- Operation ID: `get_financial_data_by_date_api_tdx_financial_data_by_date_get`
- Tags: Financial
- Summary: Get Financial Data By Date
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true); year (query, integer, required=true); mmdd (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/gb-info

- Operation ID: `get_gb_info_api_tdx_gb_info_get`
- Tags: Market
- Summary: Get Gb Info
- Request Body: `-`
- Parameters: stock_code (query, string, required=true); date_list (query, string, required=false); count (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/gp-one-data

- Operation ID: `get_gp_one_data_api_tdx_gp_one_data_get`
- Tags: Financial
- Summary: Get Gp One Data
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/gpjy-value

- Operation ID: `get_gpjy_value_api_tdx_gpjy_value_get`
- Tags: Value
- Summary: Get Gpjy Value
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true); start_time (query, string, required=false); end_time (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/gpjy-value-by-date

- Operation ID: `get_gpjy_value_by_date_api_tdx_gpjy_value_by_date_get`
- Tags: Value
- Summary: Get Gpjy Value By Date
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=true); year (query, integer, required=true); mmdd (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/ipo-info

- Operation ID: `get_ipo_info_api_tdx_ipo_info_get`
- Tags: ETF
- Summary: Get Ipo Info
- Request Body: `-`
- Parameters: ipo_type (query, integer, required=false); ipo_date (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/kzz-info

- Operation ID: `get_kzz_info_api_tdx_kzz_info_get`
- Tags: ETF
- Summary: Get Kzz Info
- Request Body: `-`
- Parameters: stock_code (query, string, required=true); fields (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/market-data

- Operation ID: `get_market_data_api_tdx_market_data_get`
- Tags: Market
- Summary: Get Market Data
- Request Body: `-`
- Parameters: stocks (query, string, required=true); fields (query, string, required=false); period (query, string, required=false); start_time (query, string, required=false); end_time (query, string, required=false); dividend_type (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/market-snapshot

- Operation ID: `get_market_snapshot_api_tdx_market_snapshot_get`
- Tags: Market
- Summary: Get Market Snapshot
- Request Body: `-`
- Parameters: stock_code (query, string, required=true); fields (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/more-info

- Operation ID: `get_more_info_api_tdx_more_info_get`
- Tags: Stock
- Summary: Get More Info
- Request Body: `-`
- Parameters: stock_code (query, string, required=true); fields (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/refresh-cache

- Operation ID: `refresh_cache_api_tdx_refresh_cache_post`
- Tags: Market
- Summary: Refresh Cache
- Request Body: `-`
- Parameters: market (query, string, required=false); force (query, boolean, required=false)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/refresh-kline

- Operation ID: `refresh_kline_api_tdx_refresh_kline_post`
- Tags: Market
- Summary: Refresh Kline
- Request Body: `-`
- Parameters: stock_list (query, string, required=false); period (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/relation

- Operation ID: `get_relation_api_tdx_relation_get`
- Tags: Stock
- Summary: Get Relation
- Request Body: `-`
- Parameters: stock_code (query, string, required=true)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/rename-sector

- Operation ID: `rename_sector_api_tdx_rename_sector_post`
- Tags: Sector
- Summary: Rename Sector
- Request Body: `SectorRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/scjy-value

- Operation ID: `get_scjy_value_api_tdx_scjy_value_get`
- Tags: Value
- Summary: Get Scjy Value
- Request Body: `-`
- Parameters: fields (query, string, required=true); start_time (query, string, required=false); end_time (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/scjy-value-by-date

- Operation ID: `get_scjy_value_by_date_api_tdx_scjy_value_by_date_get`
- Tags: Value
- Summary: Get Scjy Value By Date
- Request Body: `-`
- Parameters: fields (query, string, required=true); year (query, integer, required=true); mmdd (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/sector-list

- Operation ID: `get_sector_list_api_tdx_sector_list_get`
- Tags: Sector
- Summary: Get Sector List
- Request Body: `-`
- Parameters: list_type (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## POST /api/tdx/send-user-block

- Operation ID: `send_user_block_api_tdx_send_user_block_post`
- Tags: Sector
- Summary: Send User Block
- Request Body: `SectorRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/stock-info

- Operation ID: `get_stock_info_api_tdx_stock_info_get`
- Tags: Stock
- Summary: Get Stock Info
- Request Body: `-`
- Parameters: stock_code (query, string, required=true)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/stock-list

- Operation ID: `get_stock_list_api_tdx_stock_list_get`
- Tags: Stock
- Summary: Get Stock List
- Request Body: `-`
- Parameters: market (query, string, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/stock-list-in-sector

- Operation ID: `get_stock_list_in_sector_api_tdx_stock_list_in_sector_get`
- Tags: Market
- Summary: Get Stock List In Sector
- Request Body: `-`
- Parameters: block_code (query, string, required=false); block_type (query, integer, required=false); list_type (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/trackzs-etf-info

- Operation ID: `get_trackzs_etf_info_api_tdx_trackzs_etf_info_get`
- Tags: ETF
- Summary: Get Trackzs Etf Info
- Request Body: `-`
- Parameters: zs_code (query, string, required=true)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/trading-dates

- Operation ID: `get_trading_dates_api_tdx_trading_dates_get`
- Tags: Market
- Summary: Get Trading Dates
- Request Body: `-`
- Parameters: market (query, string, required=false); start_time (query, string, required=false); end_time (query, string, required=false); count (query, integer, required=false)
- Responses: 200: -; 422: HTTPValidationError

## GET /api/tdx/user-sectors

- Operation ID: `get_user_sectors_api_tdx_user_sectors_get`
- Tags: Sector
- Summary: Get User Sectors
- Request Body: `-`
- Parameters: -
- Responses: 200: -

## GET /health

- Operation ID: `health_health_get`
- Tags: -
- Summary: Health
- Request Body: `-`
- Parameters: -
- Responses: 200: -

## GET /providers

- Operation ID: `providers_providers_get`
- Tags: V1
- Summary: Providers
- Request Body: `-`
- Parameters: -
- Responses: 200: -

## POST /tdx/bridge/desired

- Operation ID: `sync_desired_tdx_bridge_desired_post`
- Tags: ExperimentalBridge
- Summary: Sync Desired
- Request Body: `SyncDesiredRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## GET /tdx/bridge/evidence/{symbol}

- Operation ID: `bridge_native_evidence_tdx_bridge_evidence__symbol__get`
- Tags: ExperimentalBridge
- Summary: Bridge Native Evidence
- Request Body: `-`
- Parameters: symbol (path, string, required=true)
- Responses: 200: object; 422: HTTPValidationError

## GET /tdx/bridge/health

- Operation ID: `bridge_health_tdx_bridge_health_get`
- Tags: ExperimentalBridge
- Summary: Bridge Health
- Request Body: `-`
- Parameters: -
- Responses: 200: object

## POST /tdx/bridge/owner

- Operation ID: `register_owner_tdx_bridge_owner_post`
- Tags: ExperimentalBridge
- Summary: Register Owner
- Request Body: `OwnerRegisterRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/poll

- Operation ID: `poll_tdx_bridge_poll_post`
- Tags: ExperimentalBridge
- Summary: Poll
- Request Body: `PollRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/result

- Operation ID: `post_result_tdx_bridge_result_post`
- Tags: ExperimentalBridge
- Summary: Post Result
- Request Body: `ResultRequest`
- Parameters: -
- Responses: 200: object; 422: HTTPValidationError

## POST /tdx/bridge/snapshot

- Operation ID: `post_snapshot_tdx_bridge_snapshot_post`
- Tags: ExperimentalBridge
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

## POST /v1/snapshots/query

- Operation ID: `query_snapshots_v1_snapshots_query_post`
- Tags: V1
- Summary: Query Snapshots
- Request Body: `TdxSnapshotQueryRequest`
- Parameters: -
- Responses: 200: -; 422: HTTPValidationError

## Schemas

- `ExecRequest`
- `FormulaCallRequest`
- `HTTPValidationError`
- `OwnerRegisterRequest`
- `PollRequest`
- `RawTdxCallRequest`
- `RejectedItem`
- `ResultRequest`
- `SectorQueryRequest`
- `SectorRequest`
- `SnapshotRequest`
- `SyncDesiredRequest`
- `TdxBarQueryRequest`
- `TdxConvertibleBondInfoQueryRequest`
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
- `TdxSnapshotQueryRequest`
- `TdxStockTradeAggregateByDateQueryRequest`
- `TdxStockTradeAggregateQueryRequest`
- `TdxTrackingEtfsQueryRequest`
- `TdxTradingDatesQueryRequest`
- `ValidationError`
