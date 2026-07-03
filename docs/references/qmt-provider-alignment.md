# QMT Provider Alignment Notes

Reviewed on 2026-06-27 against the current `src/adapter/qmt` and
`src/adapter/mock/qmt_mock.py` implementations.

This note records how QMT should converge with the provider-neutral datasource
contract. The current `/api/qmt/*` routes are legacy/native adapter wrappers.
New Mist collection code should target the normalized `/v1` datasource
contract, the same way it targets TDX.

## Current Boundary

- `src/adapter/qmt/client.py` wraps miniQMT `xtquant.xtdata` methods and still
  requires a Windows host with the QMT client running and logged in.
- `src/adapter/mock/qmt_mock.py` provides macOS/Linux development fixtures for
  the legacy QMT route surface.
- `/api/qmt/*` is not the product-facing cross-provider contract. It is useful
  for adapter diagnostics and incremental QMT bring-up.
- `/v1` is the provider-neutral contract for NestJS and Mist collection code.
  QMT support should move family by family behind this contract.

## First parity target set

| Capability family | Current QMT method candidates | Target `/v1` contract | Status |
| --- | --- | --- | --- |
| `bars` | `get_market_data`, `get_local_data`, `get_full_kline` | `/v1/bars/query` | Planned first. Normalize to the same bar fields as TDX. |
| `snapshots` | `get_full_tick` | `/v1/snapshots/query` | Planned first. Map full-tick quote fields to provider-neutral snapshot fields. |
| `calendar` | `get_trading_dates`, `get_trading_calendar`, `get_holidays` | `/v1/calendar/trading-dates/query` | Planned first. Keep date output provider-neutral. |
| `securities` | `get_stock_list`, `get_stock_list_in_sector` | `/v1/securities/query` | Planned first. Confirm market-to-sector mapping on a logged-in QMT host. |
| `security-info` | `get_instrument_detail`, `get_instrument_type` | `/v1/securities/info/query` | Planned first. Normalize native instrument keys before exposure. |
| `sector-list` | `get_sector_list` | `/v1/sectors/list/query` | Planned first. Normalize sector names/codes. |
| `sector-members` | `get_stock_list_in_sector` | `/v1/sectors/query` | Planned first. Reuse provider-neutral symbol normalization. |

## Later candidates

| Area | Current QMT method candidates | Alignment decision |
| --- | --- | --- |
| Reference/instrument data | `get_divid_factors`, `get_cb_info`, `get_ipo_info`, `get_etf_info` | Keep `/v1` responses unsupported until native shapes are verified and normalized fixtures exist. |
| Finance/report data | `get_financial_data` | Keep unsupported until table names, report periods, and field shapes are verified against real QMT. |
| Formula data/execution | None in current adapter | Keep unsupported. Do not emulate TDX formula APIs without a real QMT equivalent. |
| User-sector mutations | `create_sector`, `add_sector`, `remove_sector`, related methods | Admin/operator-only. Requires a separate admin spec before product exposure. |
| Trading/account methods | `order_stock`, `query_stock_asset`, related stubs | Outside datasource boundary. Requires a separate trading service/design. |

QMT sector mutation signatures intentionally follow xtdata native shape
(`parent_node`, `sector_name`, `overwrite`). They are not the same as TDX
legacy `create_sector(block_code, block_name)`, and neither signature is part
of the provider-neutral `/v1` product contract.

## Runtime Startup

QMT service startup remains optional in runtime checks. `QMT_SDK_PATH` and the
QMT login lifecycle are not finalized for the appliance path, so
`scripts/run-runtime-checks.ps1` must validate TDX and the appliance without
requiring a QMT Windows service. QMT live smoke should be added later as an
explicit opt-in check after the SDK path, client login, and service wrapper are
settled.

## Verification Owners

- Provider manifest parity is guarded by
  `tests/unit/test_qmt_datasource_alignment.py`.
- Legacy QMT route coverage remains in `tests/integration/test_qmt_routes.py`.
- Normalized `/v1` QMT requests should continue returning
  `PROVIDER_CAPABILITY_UNSUPPORTED` until each family gets a real QMT provider
  implementation and fixture-backed tests.
