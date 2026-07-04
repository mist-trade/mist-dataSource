# Validate external market-data SDK paths for Windows production deployment.
#
# This script intentionally does not copy SDK files. TDX/QMT SDKs are machine
# local, authorization-sensitive dependencies and should stay in their original
# installation directories.

param(
    [string]$EnvFile = ""
)

$ErrorActionPreference = "Stop"

if (-not $EnvFile) {
    $ProjectDir = $PSScriptRoot | Split-Path -Parent
    $EnvFile = Join-Path $ProjectDir ".env"
}

function Write-Step($msg) { Write-Host "`n===== $msg =====" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "  [WARN] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

function Get-EnvValue($content, $name) {
    $pattern = "(?m)^\s*$([regex]::Escape($name))\s*=\s*(.*?)\s*(?:#.*)?$"
    $match = [regex]::Match($content, $pattern)
    if (-not $match.Success) { return "" }
    return $match.Groups[1].Value.Trim().Trim('"').Trim("'")
}

if (-not (Test-Path $EnvFile)) {
    Write-Fail ".env file not found: $EnvFile"
    exit 1
}

$envContent = Get-Content $EnvFile -Raw
$appEnv = Get-EnvValue $envContent "APP_ENV"

Write-Step "Datasource SDK preflight"
Write-Ok "Env file: $EnvFile"

if ($appEnv -ne "production") {
    Write-Warn "APP_ENV=$appEnv; SDK preflight is relaxed outside production"
    exit 0
}

$tdxSdk = Get-EnvValue $envContent "TDX_SDK_PATH"
if (-not $tdxSdk) {
    Write-Fail "TDX_SDK_PATH is required in production"
    exit 1
}

if (-not (Test-Path $tdxSdk -PathType Container)) {
    Write-Fail "TDX_SDK_PATH does not exist: $tdxSdk"
    exit 1
}
Write-Ok "TDX_SDK_PATH exists: $tdxSdk"

$tqcenter = Join-Path $tdxSdk "tqcenter.py"
if (-not (Test-Path $tqcenter -PathType Leaf)) {
    Write-Fail "Missing TDX SDK module: $tqcenter"
    exit 1
}
Write-Ok "Found tqcenter.py"

$tdxParent = Split-Path $tdxSdk -Parent
$tdxDll = Join-Path $tdxParent "TPythClient.dll"
if (-not (Test-Path $tdxDll -PathType Leaf)) {
    Write-Fail "Missing TDX DLL: $tdxDll"
    Write-Host "  TDX_SDK_PATH should point to F:/quant/tdx/PYPlugins/user" -ForegroundColor Yellow
    Write-Host "  TPythClient.dll should stay in the parent directory F:/quant/tdx/PYPlugins" -ForegroundColor Yellow
    exit 1
}
Write-Ok "Found TPythClient.dll in parent directory"

$strategyFile = Join-Path $tdxSdk "mist_datasource.py"
Write-Host "  TDX strategy identity path: $strategyFile" -ForegroundColor Yellow
Write-Host "  Keep TDX_SDK_PATH stable. If it changes, clean stale strategy entries in TDX." -ForegroundColor Yellow

$qmtBridgeGatewayUrl = Get-EnvValue $envContent "QMT_BRIDGE_GATEWAY_URL"
if ($qmtBridgeGatewayUrl) {
    Write-Warn "QMT full-client bridge is configured but live provider enablement requires Windows spike evidence: $qmtBridgeGatewayUrl"
} else {
    Write-Warn "QMT full-client bridge is not configured; QMT provider remains disabled"
}

Write-Ok "SDK preflight passed"
