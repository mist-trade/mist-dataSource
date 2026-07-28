# TdxQuant Interface Coverage Matrix

Reviewed on 2026-06-27 from the official TdxQuant documentation.

This matrix defines how `mist-datasource` should cover TDX APIs while keeping
NestJS on provider-neutral `/v1` datasource contracts. The target is broad
coverage for non-trading data APIs. Trading/account execution APIs are outside
the market datasource boundary.

Product callers use `/v1` normalized routes. Realtime snapshots use the TDX
builtin bridge and its dedicated WebSocket. The old `/api/tdx/*` and
`/ws/quote/*` surfaces have been removed.

Related references:

- Live smoke reference: `docs/references/tdxquant-live-datasource-smoke.md`
- QMT alignment reference: `docs/references/qmt-provider-alignment.md`
- Official page capture:
  `docs/references/tdxquant-official-page-capture-2026-06-27.md`
- Official overview: <https://help.tdx.com.cn/quant/>
- HTTP mode:
  <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1hdhbmi50d038.html>

## Classifications

| Classification | Meaning |
| --- | --- |
| `normalized-now` | Implement or keep as a stable provider-neutral `/v1` data endpoint in the current/near phase. |
| `normalized-phase-2` | Implement after core market, calendar, sector, and security metadata endpoints. |
| `normalized-phase-3` | Implement after reference/instrument endpoints; mainly finance/report data. |
| `normalized-phase-4` | Implement formula data/execution with limits, timeout handling, and explicit errors. |
| `internal-only` | Used by Python runtime internals; exposed to NestJS only through normalized protocol. |
| `admin-only` | Potential operator/admin workflow, not ordinary market data reads. |
| `raw-only` | Diagnostic escape hatch through `/v1/raw/tdx/call`; not a stable application dependency. |
| `example-helper-not-api` | Found in examples but not verified as a native `tq.*` method. |
| `do-not-expose` | Outside datasource boundary. Requires a separate service/design if ever needed. |

## Phase 1: Core Market, Calendar, Sector, Security

| TDX method | Source | Classification | Endpoint family | QMT alignment | Test strategy |
| --- | --- | --- | --- | --- | --- |
| `get_market_data` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10g60jt68sc.html> | `normalized-now` | `bars` | Map to QMT bar/history data where available. | Native HTTP shape, `Value` wrapper fixture, `/v1/bars/query`. |
| `get_market_snapshot` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10iig4pb6e0.html> | `internal-only` | builtin realtime bridge | QMT uses its own native subscription callback. | Captured native fixture, bridge contract tests, realtime HIL. |
| `get_pricevol` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1hce2o96aktmk.html> | `normalized-now` | `price-volume` | Map to QMT lightweight quote/volume equivalent or return unsupported. | Native shape fixture, normalized response, QMT unsupported test. |
| `get_benchmark_data` | Official docs content; no stable nav page found in route scrape. | `normalized-now` if live runtime verifies shape, otherwise `normalized-phase-2` | `benchmarks` | QMT benchmark equivalent must be confirmed. | Live probe first, then fixture and normalized contract. |
| `get_trading_dates` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10q7i3702rk.html> | `normalized-now` | `calendar` | QMT has a calendar-style equivalent in current adapter shape. | Native fixture, `/v1/calendar/query`, QMT unsupported/supported test. |
| `get_stock_list` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10qo3uj48fg.html> | `normalized-now` | `securities` | QMT sector/list mapping or unsupported per market. | Market list fixture and normalized securities response. |
| `get_valid_stock_codes` | Official docs content; no stable nav page found in route scrape. | `normalized-now` if runtime verifies shape, otherwise `normalized-phase-2` | `securities` | QMT equivalent unknown; report manifest status explicitly. | Live probe first, then fixture. |
| `get_stock_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10jj7r7jol4.html> | `normalized-now` | `security-info` | QMT security info mapping or unsupported. | Native fixture and normalized metadata response. |
| `get_more_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h3rtq1hij0ac.html> | `normalized-now` | `security-info` | QMT extended metadata mapping or unsupported. | Native fixture and normalized metadata response. |
| `get_match_stkinfo` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1hdguaia2v4bo.html> | `normalized-now` | `security-search` | QMT symbol search equivalent unknown; manifest must be explicit. | Search fixture and normalized result list. |
| `get_sector_list` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r5907noko.html> | `normalized-now` | `sector-list` | QMT sector list exists in current adapter shape. | Native list fixture and normalized sector-list endpoint. |
| `get_stock_list_in_sector` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhttn72svo/mindoc-1h10r92mchgug.html> | `normalized-now` | `sector-members` | QMT sector membership exists in current adapter shape. | Native list/`Value` wrapper fixture and `/v1/sectors/query`. |

## Phase 2: Reference And Instrument Data

| TDX method | Source | Classification | Endpoint family | QMT alignment | Test strategy |
| --- | --- | --- | --- | --- | --- |
| `get_relation` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h84ec4p26qus.html> | `normalized-now` | `security-relations` via `/v1/reference/relations/query` | QMT returns `PROVIDER_CAPABILITY_UNSUPPORTED` until mapping is verified. | Fixture and normalized relation response. |
| `get_ipo_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h137jr3khrqo.html> | `normalized-now` | `ipo-info` via `/v1/reference/ipo/query` | QMT returns unsupported until mapping is verified. | Fixture, date filtering contract. |
| `get_gb_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h3ru0b1tssrc.html> | `normalized-now` | `share-capital` via `/v1/reference/share-capital/query` | QMT returns unsupported until mapping is verified. | Fixture and normalized numeric/date coercion. |
| `get_gb_info_by_date` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1hc4303vsv1fk.html> | `normalized-now` | `share-capital` via `/v1/reference/share-capital/query` | QMT returns unsupported until mapping is verified. | Fixture and date-range contract. |
| `get_divid_factors` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1ctuhthaq5qmg/mindoc-1h10hsiat36k4.html> | `normalized-now` | `dividend-factors` via `/v1/reference/dividend-factors/query` | QMT returns unsupported until mapping is verified. | Fixture and factor normalization. |
| `get_kzz_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h13a594nhvb4/mindoc-1h137euvcjn98.html> | `normalized-now` | `convertible-bonds` via `/v1/instruments/convertible-bonds/query` | QMT returns unsupported until mapping is verified. | Fixture and normalized instrument response; live shape still needs Windows smoke. |
| `get_cb_info` | Official docs content; no stable nav page found in route scrape. | `normalized-now` as compatibility native method after live verification | `convertible-bonds` via `/v1/instruments/convertible-bonds/query` with `nativeMethod=get_cb_info` | QMT returns unsupported until mapping is verified. | Fixture and live probe before product use. |
| `get_trackzs_etf_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h13a594nhvb4/mindoc-1h6hknp6pjppc.html> | `normalized-now` | `etf-info` via `/v1/instruments/tracking-etfs/query` | QMT returns unsupported until mapping is verified. | Fixture and normalized ETF response; live shape still needs Windows smoke. |

## Phase 3: Finance And Report Data

| TDX method | Source | Classification | Endpoint family | QMT alignment | Test strategy |
| --- | --- | --- | --- | --- | --- |
| `get_financial_data` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10m001ic888.html> | `normalized-now` | `financial-data` via `/v1/finance/financial-data/query` | QMT returns unsupported until mapping is verified. | Fixture and normalized statement/field model. |
| `get_financial_data_by_date` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10mdt617qss.html> | `normalized-now` | `financial-data` via `/v1/finance/financial-data/by-date/query` | QMT returns unsupported until mapping is verified. | Date-specific fixture and response model. |
| `get_gp_one_data` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10pk3rsg044.html> | `normalized-now` | `single-finance-value` via `/v1/finance/single-data/query` | QMT returns unsupported until mapping is verified. | Fixture with numeric coercion; optional runtime smoke uses this lightweight probe. |
| `get_gpjy_value` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10muc82r55k.html> | `normalized-now` | `stock-trade-aggregate` via `/v1/reports/stock-trade/query` | QMT returns unsupported until mapping is verified. | Fixture and date/market normalization. |
| `get_gpjy_value_by_date` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h2pci5gh6h7k.html> | `normalized-now` | `stock-trade-aggregate` via `/v1/reports/stock-trade/by-date/query` | QMT returns unsupported until mapping is verified. | Date-specific fixture. |
| `get_bkjy_value` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10p0ncmp5mc.html> | `normalized-now` | `sector-trade-aggregate` via `/v1/reports/sector-trade/query` | QMT returns unsupported until mapping is verified. | Fixture and sector mapping. |
| `get_bkjy_value_by_date` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10p3d31736g.html> | `normalized-now` | `sector-trade-aggregate` via `/v1/reports/sector-trade/by-date/query` | QMT returns unsupported until mapping is verified. | Date-specific fixture. |
| `get_scjy_value` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10p8op6ia9g.html> | `normalized-now` | `market-trade-aggregate` via `/v1/reports/market-trade/query` | QMT returns unsupported until mapping is verified. | Fixture and market mapping. |
| `get_scjy_value_by_date` | <https://help.tdx.com.cn/quant/docs/markdown/TdxQuant.md/mindoc-1h10pe678ta04.html> | `normalized-now` | `market-trade-aggregate` via `/v1/reports/market-trade/by-date/query` | QMT returns unsupported until mapping is verified. | Date-specific fixture. |

`get_report_data` is intentionally not exposed. It is not present in the
current official finance navigation, and the validated TDX MCP runtime returns
`-32601` for that tqcenter method name.

## Phase 4: Formula Data And Execution

| TDX method | Source | Classification | Endpoint family | QMT alignment | Test strategy |
| --- | --- | --- | --- | --- | --- |
| `formula_format_data` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hte6obagc0.html> | `normalized-now` | `formula-data` via `/v1/formulas/data/format/query` | QMT returns unsupported until mapping is verified. | Fixture and input-size validation. |
| `formula_set_data` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hsvcct5sdc.html> | `normalized-now` | `formula-data` via `/v1/formulas/data/set` | QMT returns unsupported until mapping is verified. | Fixture and timeout/error mapping. |
| `formula_set_data_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3hs08rn02uc.html> | `normalized-now` | `formula-data` via `/v1/formulas/data/set-info` | QMT returns unsupported until mapping is verified. | Fixture and timeout/error mapping. |
| `formula_get_data` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3httgemshno.html> | `normalized-now` | `formula-data` via `/v1/formulas/data/query` | QMT returns unsupported until mapping is verified. | Fixture and normalized value model. |
| `formula_get_all` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1hce2u769tljc.html> | `normalized-now` | `formula-metadata` via `/v1/formulas/metadata/query` | QMT returns unsupported until mapping is verified. | Fixture, formula list model, optional runtime smoke. |
| `formula_get_info` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1hce356csmgmo.html> | `normalized-now` | `formula-metadata` via `/v1/formulas/metadata/info/query` | QMT returns unsupported until mapping is verified. | Fixture and formula info model. |
| `formula_zb` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h3huq37005ro.html> | `normalized-now` | `formula-execution` via `/v1/formulas/zb/execute` | QMT returns unsupported until mapping is verified. | Timeout, request limit, fixture, error mapping. |
| `formula_xg` | Formula execution page/content. | `normalized-now` | `formula-execution` via `/v1/formulas/xg/execute` | QMT returns unsupported until mapping is verified. | Timeout, request limit, fixture, error mapping. |
| `formula_exp` | Formula execution page/content. | `normalized-now` | `formula-execution` via `/v1/formulas/exp/execute` | QMT returns unsupported until mapping is verified. | Timeout, request limit, fixture, error mapping. |
| `formula_process_mul_zb` | Batch formula page/content. | `normalized-now` | `formula-batch-execution` via `/v1/formulas/batch/zb/execute` | QMT returns unsupported until mapping is verified. | Timeout, batch-size limit, fixture, error mapping. |
| `formula_process_mul_xg` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h3hrvkp4sc0g/mindoc-1h4ad5lisvdfg.html> | `normalized-now` | `formula-batch-execution` via `/v1/formulas/batch/xg/execute` | QMT returns unsupported until mapping is verified. | Timeout, batch-size limit, fixture, error mapping. |
| `formula_process_mul_exp` | Batch formula page/content. | `normalized-now` | `formula-batch-execution` via `/v1/formulas/batch/exp/execute` | QMT returns unsupported until mapping is verified. | Timeout, batch-size limit, fixture, error mapping. |

## Runtime/Internal

| TDX method | Source | Classification | Endpoint family | QMT alignment | Test strategy |
| --- | --- | --- | --- | --- | --- |
| `subscribe_hq` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h1104d65vr68.html> | `internal-only` | `websocket-subscriptions` | QMT subscription equivalent can map to same WebSocket commands. | Unit tests for sync, callback dirty-marking, live optional smoke. |
| `unsubscribe_hq` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h112vh7jtsms.html> | `internal-only` | `websocket-subscriptions` | QMT subscription equivalent can map to same WebSocket commands. | Unit tests and live optional smoke. |
| `get_subscribe_hq_stock_list` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h1137r4k2mas.html> | `internal-only` | `websocket-subscriptions` | QMT equivalent unknown. | Runtime WebSocket reconciliation tests. |

## Admin/Operator Or Raw-Only Utilities

`/v1/raw/tdx/call` is a datasource operator/debug escape hatch for smoke tests,
official-doc exploration, and incident diagnostics. It is not a stable backend
dependency, and normal Mist collection code must use normalized `/v1` endpoints
or WebSocket commands instead.

| TDX method | Source | Classification | Endpoint family | QMT alignment | Test strategy |
| --- | --- | --- | --- | --- | --- |
| `refresh_cache` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10f9145us1g.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `refresh_kline` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10fh9m6recg.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `download_file` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10pqrdlj71o.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `exec_to_tdx` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h85iq443j44c.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `send_message` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10rkbndkb0k.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `send_file` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10u17ue9464.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `send_warn` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10u5k9qjh8o.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `send_bt_data` | <https://help.tdx.com.cn/quant/docs/markdown/ctx.stock.md/mindoc-1h10vc2pot87c.html> | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `send_trade_warn` | Official docs content; no stable nav page found in route scrape. | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `send_warnings_for_stocks` | Official docs content; no stable nav page found in route scrape. | `admin-only` | `provider-admin` | QMT equivalent unknown. | Admin design required before exposure. |
| `create_sector` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10rrkuj1drs.html> | `admin-only` | `user-sector-admin` | QMT equivalent unknown. | Admin design required before mutation exposure. |
| `delete_sector` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10s391lng6s.html> | `admin-only` | `user-sector-admin` | QMT equivalent unknown. | Admin design required before mutation exposure. |
| `rename_sector` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10s7n863d50.html> | `admin-only` | `user-sector-admin` | QMT equivalent unknown. | Admin design required before mutation exposure. |
| `clear_sector` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10sbcnl1c94.html> | `admin-only` | `user-sector-admin` | QMT equivalent unknown. | Admin design required before mutation exposure. |
| `get_user_sector` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h1hauh9inaac.html> | `admin-only` for now | `user-sector-admin` | QMT equivalent unknown. | May become read-only data after admin design. |
| `send_user_block` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h139a4ckchkk/mindoc-1h10sec960u0c.html> | `admin-only` | `user-sector-admin` | QMT equivalent unknown. | Admin design required before mutation exposure. |

## Example Helpers And Non-APIs

| Name | Source | Classification | Notes |
| --- | --- | --- | --- |
| `get_real_time_data` | <https://help.tdx.com.cn/quant/docs/markdown/gzh0122inweixinwenz/gzh20260302wzlz.html> | `example-helper-not-api` | Found as a user-defined helper in `订阅Handlebar.py`; it calls `tq.get_market_data(...)` internally. Do not implement unless native `tq.get_real_time_data` is verified in runtime. |

## Do Not Expose: Trading And Account

| TDX method | Source | Classification | Reason |
| --- | --- | --- | --- |
| `stock_account` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h7k4iqb1grk4/mindoc-1h7k4k5tk6q64.html> | `do-not-expose` | Account/trading boundary. |
| `query_stock_asset` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h7k4iqb1grk4/mindoc-1h84fvcjulrnc.html> | `do-not-expose` | Account/trading boundary. |
| `query_stock_orders` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h7k4iqb1grk4/mindoc-1h7k4rp481gt4.html> | `do-not-expose` | Account/trading boundary. |
| `query_stock_positions` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h7k4iqb1grk4/mindoc-1h7k5ar9kc508.html> | `do-not-expose` | Account/trading boundary. |
| `order_stock` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h7k4iqb1grk4/mindoc-1h7k5j4drr928.html> | `do-not-expose` | Order execution requires a separate audited trading service. |
| `cancel_order_stock` | <https://help.tdx.com.cn/quant/docs/markdown/mindoc-1h7k4iqb1grk4/mindoc-1h84elp5atr6o.html> | `do-not-expose` | Order cancellation requires a separate audited trading service. |
