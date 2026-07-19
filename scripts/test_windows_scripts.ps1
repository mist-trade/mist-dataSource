param(
    [string]$ProjectDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectDir) {
    $ProjectDir = $PSScriptRoot | Split-Path -Parent
}
$ProjectDir = [System.IO.Path]::GetFullPath($ProjectDir)
$TestRoot = Join-Path $ProjectDir ".test-windows-scripts"

function Assert-Equal {
    param(
        [string]$Name,
        $Expected,
        $Actual
    )

    if ($Expected -ne $Actual) {
        throw "$Name failed. Expected: <$Expected>. Actual: <$Actual>."
    }
    Write-Host "  [PASS] $Name" -ForegroundColor Green
}

function Assert-Match {
    param(
        [string]$Name,
        [string]$Actual,
        [string]$Pattern
    )

    if ($Actual -notmatch [regex]::Escape($Pattern)) {
        throw "$Name failed. Expected pattern: <$Pattern>. Actual: <$Actual>."
    }
    Write-Host "  [PASS] $Name" -ForegroundColor Green
}

if (Test-Path $TestRoot) {
    Remove-Item $TestRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $TestRoot | Out-Null

$uvTestProjectDir = Join-Path $TestRoot "uv-project"
$uvRuntimeDir = Join-Path $uvTestProjectDir "runtime"
New-Item -ItemType Directory -Force -Path $uvRuntimeDir | Out-Null
$uvRuntimeFile = Join-Path $uvRuntimeDir "uv.exe"
if (-not (Test-Path $uvRuntimeFile -PathType Leaf)) {
    Set-Content -Path $uvRuntimeFile -Value "test uv" -Encoding UTF8
}

. "$PSScriptRoot\windows-common.ps1"

Assert-Equal `
    "env parsing trims quotes" `
    "F:/quant/tdx/PYPlugins/user" `
    (Get-EnvValue "TDX_SDK_PATH=`"F:/quant/tdx/PYPlugins/user`"" "TDX_SDK_PATH")

$windowsEnvExample = Get-Content (Join-Path $ProjectDir ".env.windows.example") -Raw
$deployWindows = Get-Content (Join-Path $ProjectDir "scripts\deploy_windows.ps1") -Raw
$runtimeChecks = Get-Content (Join-Path $ProjectDir "scripts\run-runtime-checks.ps1") -Raw
$tdxWinswInstall = Get-Content (Join-Path $ProjectDir "scripts\winsw\install-tdx-datasource.ps1") -Raw
$tdxWinswSmoke = Get-Content (Join-Path $ProjectDir "scripts\winsw\test-tdx-datasource.ps1") -Raw
$qmtWinswInstall = Get-Content (Join-Path $ProjectDir "scripts\winsw\install-qmt-datasource.ps1") -Raw
$qmtWinswSmoke = Get-Content (Join-Path $ProjectDir "scripts\winsw\test-qmt-datasource.ps1") -Raw
Assert-Match "default TDX SDK path" $windowsEnvExample "TDX_SDK_PATH=F:/quant/tdx/PYPlugins/user"
Assert-Match "default QMT bridge gateway" $windowsEnvExample "QMT_BRIDGE_GATEWAY_URL=http://127.0.0.1:9002/qmt/bridge"
if ($windowsEnvExample -match "QMT_LOCAL_DAT" -or $qmtWinswInstall -match "QMT_LOCAL_DAT") {
    throw "QMT datasource configuration must not contain local DAT settings."
}
Write-Host "  [PASS] QMT datasource has no local DAT settings" -ForegroundColor Green
Assert-Match "TDX comment points SDK path to user directory" $windowsEnvExample "TDX_SDK_PATH points to the user directory that contains tqcenter.py."
Assert-Match "TDX comment keeps DLL in parent directory" $windowsEnvExample "TPythClient.dll stays one level above TDX_SDK_PATH."
Assert-Match "default uv python package index" $windowsEnvExample "UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple"
Assert-Match "default uv python version" $windowsEnvExample "UV_PYTHON=3.12"
Assert-Match "deploy script checks python launcher" $deployWindows "Get-Command py"
Assert-Match "deploy script lets uv handle missing python" $deployWindows "uv sync will create/find Python 3.12"
Assert-Match "deploy script configures uv default index" $deployWindows "--default-index"
Assert-Match "deploy script defaults to Tsinghua python package index" $deployWindows "https://pypi.tuna.tsinghua.edu.cn/simple"
Assert-Match "deploy script pins uv sync python" $deployWindows "--python"
Assert-Match "deploy script defaults to Python 3.12" $deployWindows 'if (-not $uvPython) { $uvPython = "3.12" }'
Assert-Match "deploy script syncs from frozen lockfile" $deployWindows "--frozen"
Assert-Match "deploy script no longer supports service-only step" $deployWindows "Use: install, test"
Assert-Match "deploy script documents no service registration" $deployWindows "不再注册 Windows 服务"
if ($deployWindows -match [regex]::Escape('--locked')) {
    throw "deploy script must use --frozen, not --locked, during appliance installs."
}
Write-Host "  [PASS] deploy script avoids lockfile freshness checks" -ForegroundColor Green
Assert-Match "deploy script logs uv sync output" $deployWindows "uv-sync.log"
Assert-Match "deploy script prints uv sync failure tail" $deployWindows "Recent uv sync output"
if ($deployWindows -match [regex]::Escape('Step 5/5')) {
    throw "deploy script must not include a service registration step."
}
Write-Host "  [PASS] deploy script has no service registration step" -ForegroundColor Green
if ($deployWindows -match [regex]::Escape('nssm status MistTDX / MistQMT')) {
    throw "deploy script must not print NSSM commands in appliance install completion guidance."
}
Write-Host "  [PASS] deploy script avoids NSSM completion guidance" -ForegroundColor Green
if ($deployWindows -match [regex]::Escape('2>$null | Out-Null')) {
    throw "deploy script must not hide uv sync stderr/stdout."
}
Write-Host "  [PASS] deploy script keeps uv sync output visible" -ForegroundColor Green
Assert-Match "TDX WinSW installer accepts started-successfully output" $tdxWinswInstall "started successfully"
Assert-Match "TDX WinSW installer clears native exit code after success" $tdxWinswInstall '$global:LASTEXITCODE = 0'
Assert-Match "TDX WinSW installer resolves packaged uv" $tdxWinswInstall "Resolve-UvExe"
Assert-Match "TDX WinSW installer default executable can be resolved" $tdxWinswInstall 'if (-not $Executable)'
Assert-Match "QMT WinSW installer starts qmt app" $qmtWinswInstall "qmt.main:app"
Assert-Match "QMT WinSW installer defaults port 9002" $qmtWinswInstall '[int]$DatasourcePort = 9002'
Assert-Match "QMT WinSW installer uses distinct service" $qmtWinswInstall 'mist-qmt-datasource'
Assert-Match "QMT WinSW installer resolves packaged uv" $qmtWinswInstall "Resolve-UvExe"
Assert-Match "QMT WinSW installer explains manual strategy registration" $qmtWinswInstall "manual"
foreach ($forbidden in @("TDX_SDK_PATH", "tqcenter.py", "mist_datasource.py")) {
    if ($qmtWinswInstall -match [regex]::Escape($forbidden)) {
        throw "QMT WinSW installer must not manage TDX SDK or strategy identity: $forbidden"
    }
}
Write-Host "  [PASS] QMT WinSW installer avoids strategy and TDX SDK management" -ForegroundColor Green
Assert-Match "TDX WinSW smoke uses supported market data method" $tdxWinswSmoke "get_market_data"
Assert-Match "TDX WinSW smoke uses read-only websocket ping" $tdxWinswSmoke '"type" = "ping"'
Assert-Match "TDX WinSW smoke preserves dotted symbols for TDX HTTP" $tdxWinswSmoke "ConvertTo-TdxHttpSymbol"
Assert-Match "QMT WinSW smoke checks health" $qmtWinswSmoke "/health"
Assert-Match "QMT WinSW smoke checks bridge health" $qmtWinswSmoke "/qmt/bridge/health"
Assert-Match "QMT WinSW smoke checks bridge owner field" $qmtWinswSmoke "ownerId"
Assert-Match "QMT WinSW smoke does not use websocket" $qmtWinswSmoke "HTTP polling bridge"
if ($qmtWinswSmoke -match [regex]::Escape('/ws/quote')) {
    throw "QMT WinSW smoke must not use WebSocket routes."
}
Write-Host "  [PASS] QMT WinSW smoke stays HTTP-only" -ForegroundColor Green
if ($tdxWinswSmoke -match [regex]::Escape('method = "ping"')) {
    throw "TDX WinSW smoke must not call unsupported raw ping."
}
Write-Host "  [PASS] TDX WinSW smoke avoids unsupported raw ping" -ForegroundColor Green
if ($tdxWinswSmoke -match [regex]::Escape('"type" = "sync_subscriptions"')) {
    throw "TDX WinSW smoke must not change subscriptions when backend owns the TDX leader."
}
Write-Host "  [PASS] TDX WinSW smoke avoids subscription mutation" -ForegroundColor Green
if ($tdxWinswInstall -match [regex]::Escape('("refresh")')) {
    throw "TDX WinSW installer must not call refresh; older bundled WinSW builds do not support it."
}
Write-Host "  [PASS] TDX WinSW installer avoids unsupported refresh command" -ForegroundColor Green
Assert-Match "runtime checks run script self-test" $runtimeChecks "scripts\test_windows_scripts.ps1"
Assert-Match "runtime checks can require source self-test" $runtimeChecks "RequireScriptSelfTest"
Assert-Match "runtime checks knows source-only env example" $runtimeChecks ".env.windows.example"
Assert-Match "runtime checks run SDK preflight" $runtimeChecks "scripts\preflight-sdk.ps1"
Assert-Match "runtime checks can run datasource deploy install" $runtimeChecks "-Only install"
Assert-Match "runtime checks can run datasource deploy test" $runtimeChecks "-Only test"
Assert-Match "runtime checks run WinSW service probe" $runtimeChecks "scripts\winsw\test-tdx-datasource.ps1"
Assert-Match "runtime checks pass WebSocket skip to WinSW probe" $runtimeChecks '$winswProbeArgs += "-SkipWebSocket"'
Assert-Match "WinSW probe accepts WebSocket skip" $tdxWinswSmoke '[switch]$SkipWebSocket'
Assert-Match "WinSW probe guards WebSocket check" $tdxWinswSmoke 'if (-not $SkipWebSocket)'
Assert-Match "runtime checks checks TDX service status" $runtimeChecks "mist-tdx-datasource"
Assert-Match "runtime checks points to TDX service logs" $runtimeChecks "logs\mist-tdx-datasource"
Assert-Match "runtime checks run appliance health check" $runtimeChecks "health-check.ps1"
Assert-Match "runtime checks query normalized bars" $runtimeChecks "/v1/bars/query"
Assert-Match "runtime checks query normalized snapshots" $runtimeChecks "/v1/snapshots/query"
Assert-Match "runtime checks query sectors" $runtimeChecks "/v1/sectors/query"
Assert-Match "runtime checks query provider manifest" $runtimeChecks "/providers"
Assert-Match "runtime checks require TDX provider manifest" $runtimeChecks 'foreach ($providerId in @("tdx"))'
if ($runtimeChecks -match [regex]::Escape('foreach ($providerId in @("tdx", "qmt"))')) {
    throw "runtime checks must not require QMT in the TDX provider manifest."
}
Assert-Match "runtime checks reject QMT provider manifest" $runtimeChecks "TDX provider manifest must not include provider 'qmt'"
Write-Host "  [PASS] runtime checks do not require QMT provider manifest" -ForegroundColor Green
Assert-Match "runtime checks query sector list" $runtimeChecks "/v1/sectors/list/query"
Assert-Match "runtime checks query trading dates" $runtimeChecks "/v1/calendar/trading-dates/query"
Assert-Match "runtime checks query securities" $runtimeChecks "/v1/securities/query"
Assert-Match "runtime checks query security info" $runtimeChecks "/v1/securities/info/query"
Assert-Match "runtime checks query price volume" $runtimeChecks "/v1/price-volume/query"
Assert-Match "runtime checks support optional reference smoke" $runtimeChecks "IncludeReferenceInstrumentSmoke"
Assert-Match "runtime checks verify raw TDX share-capital data" $runtimeChecks "get_gb_info"
Assert-Match "runtime checks query normalized relations data" $runtimeChecks "/v1/reference/relations/query"
Assert-Match "runtime checks query normalized IPO data" $runtimeChecks "/v1/reference/ipo/query"
Assert-Match "runtime checks query normalized share-capital data" $runtimeChecks "/v1/reference/share-capital/query"
Assert-Match "runtime checks query normalized dividend-factor data" $runtimeChecks "/v1/reference/dividend-factors/query"
Assert-Match "runtime checks query normalized convertible bond data" $runtimeChecks "/v1/instruments/convertible-bonds/query"
Assert-Match "runtime checks query normalized tracking ETF data" $runtimeChecks "/v1/instruments/tracking-etfs/query"
Assert-Match "runtime checks support optional finance smoke" $runtimeChecks "IncludeFinanceReportSmoke"
Assert-Match "runtime checks verify raw TDX finance data" $runtimeChecks "get_gp_one_data"
Assert-Match "runtime checks use TDX finance table list parameter" $runtimeChecks "table_list = @(`$FinanceField)"
Assert-Match "runtime checks query normalized financial data" $runtimeChecks "/v1/finance/financial-data/query"
Assert-Match "runtime checks query normalized financial data by date" $runtimeChecks "/v1/finance/financial-data/by-date/query"
Assert-Match "runtime checks query normalized finance data" $runtimeChecks "/v1/finance/single-data/query"
Assert-Match "runtime checks query normalized stock trade report data" $runtimeChecks "/v1/reports/stock-trade/query"
Assert-Match "runtime checks query normalized stock trade report data by date" $runtimeChecks "/v1/reports/stock-trade/by-date/query"
Assert-Match "runtime checks query normalized sector trade report data" $runtimeChecks "/v1/reports/sector-trade/query"
Assert-Match "runtime checks query normalized sector trade report data by date" $runtimeChecks "/v1/reports/sector-trade/by-date/query"
Assert-Match "runtime checks query normalized market trade report data" $runtimeChecks "/v1/reports/market-trade/query"
Assert-Match "runtime checks query normalized market trade report data by date" $runtimeChecks "/v1/reports/market-trade/by-date/query"
if ($runtimeChecks -match [regex]::Escape('/v1/reports/data/query')) {
    throw "runtime checks must not call removed /v1/reports/data/query."
}
Write-Host "  [PASS] runtime checks avoids removed report data endpoint" -ForegroundColor Green
Assert-Match "runtime checks support optional formula smoke" $runtimeChecks "IncludeFormulaSmoke"
Assert-Match "runtime checks verify raw TDX formula metadata" $runtimeChecks "formula_get_all"
Assert-Match "runtime checks query normalized formula metadata" $runtimeChecks "/v1/formulas/metadata/query"
Assert-Match "runtime checks verify raw TDX market data" $runtimeChecks "get_market_data"
Assert-Match "runtime checks accept unwrapped raw market data" $runtimeChecks "Raw get_market_data direct result"
Assert-Match "runtime checks verify raw TDX snapshot" $runtimeChecks "get_market_snapshot"
Assert-Match "runtime checks use TDX HTTP dotted symbol default" $runtimeChecks '[string]$Symbol = "600519.SH"'
Assert-Match "runtime checks use TDX sector block default" $runtimeChecks '[string]$Sector = "通达信88"'
Assert-Match "runtime checks preserve dotted symbols for TDX HTTP" $runtimeChecks "ConvertTo-TdxHttpSymbol"
Assert-Match "runtime checks can explicitly allow websocket subscription changes" $runtimeChecks "AllowWebSocketSubscriptionChange"
Assert-Match "runtime checks support optional live quote wait" $runtimeChecks "RequireLiveQuote"
Assert-Match "runtime checks verify live quote snapshot payload" $runtimeChecks '$message.data.snapshot'
Assert-Match "runtime checks unsubscribe after websocket smoke" $runtimeChecks '"type" = "unsubscribe"'
if ($runtimeChecks -match [regex]::Escape('MistQMT')) {
    throw "runtime checks must not require a QMT service until full-QMT bridge evidence is finalized."
}
Write-Host "  [PASS] runtime checks do not require QMT service startup" -ForegroundColor Green

Assert-Equal `
    "blank env returns empty string" `
    "" `
    (Get-EnvValue "APP_ENV=production" "QMT_BRIDGE_GATEWAY_URL")

Assert-Equal `
    "uv fallback resolves packaged runtime" `
    (Resolve-FullPath (Join-Path $uvTestProjectDir "runtime\uv.exe")) `
    (Resolve-UvExe -ProjectDir $uvTestProjectDir -PreferPathLookup:$false)
if (Test-Path $TestRoot) {
    Remove-Item $TestRoot -Recurse -Force
}

Write-Host "`nWindows script tests passed." -ForegroundColor Green
