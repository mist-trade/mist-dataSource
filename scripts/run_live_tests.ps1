# Run live integration tests for TDX service on Windows.
#
# Requirements:
# - Windows OS
# - TDX terminal installed and running
# - APP_ENV=production environment variable set
#
# Usage:
#   .\scripts\run_live_tests.ps1
#
# Note: Only run on Windows with TDX terminal running.

$env:APP_ENV = "production"
uv run pytest tests/integration/test_tdx_live.py -v -m live

Write-Host "Live tests completed."
Write-Host ""
Write-Host "Note: If you see import errors, make sure:"
Write-Host "  1. TDX terminal is running"
Write-Host "  2. TDX_SDK_PATH environment variable is set"
Write-Host "  3. Strategy is registered in TDX terminal (check for duplicate strategy names)"
