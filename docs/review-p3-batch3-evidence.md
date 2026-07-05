# Review P3 Batch 3 Evidence: mist-datasource

## Selected Review IDs

| Review ID | Classification | Files / Evidence | Verification |
|---|---|---|---|
| CODE_REVIEW L4 | implemented | `src/adapter_legacy/tdx/client.py` | TDX heartbeat now uses `get_logger` instead of `print`. |
| INFRA_REVIEW S3 | deferred | datasource script examples | Hardcoded example paths remain deployment documentation work. |
| INFRA_REVIEW S4 | partially closed | `scripts/windows-common.ps1`, WinSW scripts | Shared helper exists for primary scripts; remaining script-local helpers are deferred to script pass. |
| INFRA_REVIEW T2 | implemented | `.pre-commit-config.yaml`, `uv.lock` | Ruff pre-commit rev matches locked `ruff` version. |
| CODE_SMELL_REVIEW D2.1 | implemented | `src/core/exceptions.py`, `src/core/__init__.py` | Removed unused `ConnectionError` and `ConfigurationError`. |
| CODE_SMELL_REVIEW D2.3 | deferred | legacy service layer | Service-layer deletion stays tied to legacy route deprecation. |
| CODE_SMELL_REVIEW D2.4 | implemented | `tdx/services/tdx_service.py` | Removed unused serializer helper. |
| CODE_SMELL_REVIEW D2.5 | superseded | legacy QMT adapter removed | QMT no longer uses the adapter package. |
| CODE_SMELL_REVIEW R2.2 | deferred | normalization helpers | Broad optional-string conversion pass deferred. |
| CODE_SMELL_REVIEW R2.3 | already closed | `src/datasource/tdx_normalization.py` | `_to_tdx_native_date` is no longer present. |
| CODE_SMELL_REVIEW P2.3 | already closed | `src/datasource/tdx_normalization.py` | Only one `_as_sequence` remains. |
| CODE_SMELL_REVIEW P2.5 | deferred | QMT mock adapter | Mock data duplication deferred to mock fixture pass. |
| CODE_SMELL_REVIEW T2.4 | already closed | `tdx/routes/v1/product.py` | `_call_provider` operation is typed as `Callable`. |
| CODE_SMELL_REVIEW M2.4 | deferred | market defaults | Market default constants deferred to provider contract pass. |
| CODE_SMELL_REVIEW N2.1 | implemented | `src/core/exceptions.py` | Removed custom `ConnectionError` shadowing the built-in name. |
| CODE_SMELL_REVIEW N2.2 | deferred | `tdx_normalization.py` native value helpers | Native helper naming pass deferred. |
| CODE_SMELL_REVIEW N2.3 | implemented | `src/datasource/tdx_normalization.py`, bridge/subscription | Centralized stable and normalized dedupe helpers. |
| CODE_SMELL_REVIEW C2.2 | superseded | legacy QMT adapter removed | QMT native V1 path replaces the old adapter branch. |
| CODE_SMELL_REVIEW C2.3 | deferred | `_load_tq_module` docstring | Docstring wording deferred to TDX SDK loading docs pass. |
| CODE_SMELL_REVIEW C2.4 | deferred | TDX adapter TODOs | TODO ownership pass deferred. |
| CODE_SMELL_REVIEW C2.5 | implemented | touched datasource files | Removed selected stale/noisy comments in touched code. |
| CODE_SMELL_REVIEW U2.2 | implemented | `src/adapter_legacy/tdx/client.py` | Heartbeat logging now uses logger. |
| CODE_SMELL_REVIEW U2.4 | already closed | route helpers | Old `_get_adapter` helper is gone; v1 uses `_get_provider`. |
| CODE_SMELL_REVIEW O2.3 | superseded | legacy QMT adapter removed | Dead `list_type` branch no longer exists in source. |
| CODE_SMELL_REVIEW O2.5 | deferred | `src/datasource/tdx/runtime.py` | `_read_*` helper consolidation deferred to runtime-health pass. |

## Red Verification

- `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/test_repository_hygiene.py -q`
  failed as expected because pre-commit used `v0.8.0` while `uv.lock` has
  `ruff 0.15.18`, and because unused exception classes were still present.
- An intermediate run of focused tests/ruff caught missing `Iterable` and
  `normalize_symbol` imports after dedupe helper extraction.

## Green Verification

- `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/test_repository_hygiene.py -q`
  passed: 17 tests.
- `UV_CACHE_DIR=.uv-cache uv run pytest tests/unit/test_repository_hygiene.py tests/unit/test_tdx_legacy/bridge.py tests/unit/test_tdx_runtime.py tests/unit/test_tdx_normalization.py -q`
  passed: 50 tests.
- `UV_CACHE_DIR=.uv-cache uv run ruff check ...touched files...` passed.
- `UV_CACHE_DIR=.uv-cache uv run ruff format --check ...touched Python files...`
  passed.
- `UV_CACHE_DIR=.uv-cache uv run pyright` passed with 0 errors.
