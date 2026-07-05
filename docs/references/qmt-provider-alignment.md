# QMT Provider Alignment Notes

Reviewed on 2026-07-04 against the full-QMT built-in Python direction.

This note records how QMT should converge with the provider-neutral datasource
contract. New Mist collection code should target the normalized `/v1`
datasource contract, the same way it targets TDX. QMT provider implementation
must use the full QMT client's built-in Python bridge after Windows spike
evidence validates the runtime.

## Current Boundary

- Production QMT access through the old local SDK adapter path is removed.
- `qmt/builtin_bridge/mist_qmt_bridge.py` is the default full-QMT built-in
  Python scaffold. It currently uses standard-library HTTP polling and one
  serial command lane, but production transport remains spike-gated.
- The bridge must run as one normal QMT built-in strategy script. Do not enable
  the editor's separate-process option for the production bridge, because it
  changes the runtime boundary away from the controlled built-in script model.
- WebSocket duplex is a first-class Windows spike candidate. QMT must initiate
  the outbound connection to the datasource gateway; after that, the datasource
  may push command messages over the same connection.
- The WebSocket spike must prove more than connectivity. In
  `mode=spike-command-loop`, the datasource pushes a health command and a
  `get_market_data_ex` command to the QMT script; the script executes both in
  one bounded single-thread loop and returns structured results on the same
  connection.
- The current bridge scaffold is driven by `run_time` so the spike can prove
  whether timer callbacks fire outside trading hours. Production must not rely
  on `run_time` until that evidence is captured. It also must not depend on
  `handlebar` K-line events or `subscribe` quote callbacks for command intake.
- `qmt/builtin_bridge/mist_qmt_spike.py` is the Windows evidence script for
  library/network capability and process/execution-model checks.
- `src/adapter/mock/qmt_mock.py` remains the macOS/Linux development fixture for
  legacy route tests and contract fixtures.
- `/api/qmt/*` is not the product-facing cross-provider contract. It is a
  diagnostic or migration surface until normalized QMT provider routes are
  promoted.
- `/v1` is the provider-neutral contract for NestJS and Mist collection code.

## First Parity Target Set

| Capability family | Full-QMT method candidates | Target `/v1` contract | Status |
| --- | --- | --- | --- |
| `bars` | configured local DAT reader for historical `1d`/`1m`/`5m`; bridge-backed native bars later | `/v1/bars/query` | Supported for configured local DAT historical bars; bridge-native bars remain spike-gated. |
| `snapshots` | `get_full_tick` | `/v1/snapshots/query` | Spike-blocked until native shape is captured. |
| `calendar` | trading calendar functions from built-in docs | `/v1/calendar/trading-dates/query` | Spike-blocked until native shape is captured. |
| `securities` | sector/list functions from built-in docs | `/v1/securities/query` | Spike-blocked until mapping is verified. |
| `security-info` | instrument detail functions from built-in docs | `/v1/securities/info/query` | Spike-blocked until mapping is verified. |
| `sector-list` | sector list functions from built-in docs | `/v1/sectors/list/query` | Spike-blocked until mapping is verified. |
| `sector-members` | `get_stock_list_in_sector` | `/v1/sectors/query` | Spike-blocked until native shape is captured. |

## Later Candidates

| Area | Alignment decision |
| --- | --- |
| Reference/instrument data | Keep `/v1` responses unsupported until native shapes are verified and normalized fixtures exist. |
| Finance/report data | Keep unsupported until table names, report periods, and field shapes are verified against full QMT. |
| Formula data/execution | Keep unsupported until full-QMT formula capabilities and limits are verified. |
| User-sector mutations | Admin/operator-only. Requires a separate admin spec before product exposure. |
| Account/trading methods | Out of scope for this market datasource. Requires a separate trading/account design. |

## Runtime Startup

QMT live startup remains disabled in runtime checks until both Windows spikes
are captured. The default bridge model is:

1. Mist datasource command gateway runs outside QMT.
2. A single normal full-QMT built-in Python script owns one outbound command
   channel to the gateway.
3. The bridge executes one command lane serially.
4. The datasource exposes only normalized `/v1` and WebSocket contracts to
   backend consumers.

The open transport question is HTTP polling versus WebSocket duplex. WebSocket
can become the production transport only if the Windows spike proves QMT can
keep a normal single-script WebSocket client connected, receive
datasource-pushed commands, execute QMT native calls, return results
bidirectionally, recover cleanly, and avoid blocking QMT. The timer question is
separate: if WebSocket still needs a pump callback, `run_time` must be proven to
fire outside trading hours before production can depend on it.

## Local DAT Bars Fast Path

Full-QMT historical downloads can be read from the local `datadir` as a
bars-only fast path for `1d`, `1m`, and `5m`. This path is not a bridge
replacement. It is only for historical `/v1/bars/query` responses after the
operator has explicitly configured the full-QMT data directory.

Default safeguards:

1. `QMT_LOCAL_DAT_ENABLED` must be enabled before the reader is considered.
2. `QMT_LOCAL_DAT_DIR` must point to the full-QMT data directory.
3. `QMT_LOCAL_DAT_BLOCK_AFTER` defaults to `18:00` China time so reads avoid
   the operator's evening update job.
4. `QMT_LOCAL_DAT_ON_BLOCK` chooses `retryable_error`, `fallback_bridge`, or
   `allow`; the default is `fallback_bridge`.
5. The reader must stat the file before and after a short wait. If size or
   modification time changes, the file is treated as unstable and is not
   parsed.

DAT data must normalize into the same bar contract as bridge-backed QMT bars:
same symbol format, period, `barTime`, OHLCV fields, `amount`, `receivedAt`,
and `provider=qmt`. Non-bars provider families must not use DAT files.

Third-party packages, local port listening, threads, processes, subprocesses,
and QMT editor separate-process execution remain outside the default production
bridge unless separate Windows evidence proves them safe and follow-up design
work approves them.

## Verification Owners

- Provider manifest parity is guarded by
  `tests/unit/test_qmt_datasource_alignment.py`.
- Full-QMT bridge guardrails are guarded by
  `tests/unit/test_bigqmt_bridge_guardrails.py`.
- Command gateway behavior is guarded by
  `tests/unit/test_qmt_command_gateway.py`.
- Normalized `/v1` QMT requests should continue returning explicit unavailable
  or unsupported responses until each family gets a real full-QMT provider
  implementation and fixture-backed tests.
