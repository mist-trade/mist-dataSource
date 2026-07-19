param(
    [string]$DatasourceDir = "",
    [string]$ApplianceRoot = "",
    [string]$EnvFile = "",
    [string]$BaseUrl = "http://127.0.0.1:9001",
    [string]$WsUrl = "",
    [string]$ClientId = "runtime-smoke",
    [string]$Symbol = "600519.SH",
    [string]$RawSymbol = "",
    [string]$Sector = "通达信88",
    [string]$SectorTradeCode = "880081.SH",
    [string]$ConvertibleBondSymbol = "123039.SZ",
    [string]$TrackingEtfIndexSymbol = "950162.CSI",
    [string]$FinanceField = "GO1",
    [string]$FinancialDataField = "FN193",
    [string]$FinancialDataByDateField = "FN194",
    [string]$StockTradeField = "GP3",
    [string]$StockTradeByDateField = "GP1",
    [string]$SectorTradeField = "BK5",
    [string]$SectorTradeByDateField = "BK9",
    [string]$MarketTradeField = "SC1",
    [string]$MarketTradeByDateField = "SC10",
    [string]$Period = "1d",
    [int]$Count = 2,
    [int]$TimeoutSeconds = 20,
    [int]$LiveQuoteTimeoutSeconds = 60,
    [string]$TdxServiceName = "mist-tdx-datasource",
    [switch]$RunDatasourceInstall,
    [switch]$RunDatasourceStartupTest,
    [switch]$SkipScriptSelfTest,
    [switch]$RequireScriptSelfTest,
    [switch]$SkipSdkPreflight,
    [switch]$SkipWinSWProbe,
    [switch]$SkipApplianceHealth,
    [switch]$SkipMySQL,
    [switch]$SkipSmoke,
    [switch]$SkipWebSocket,
    [switch]$IncludeReferenceInstrumentSmoke,
    [switch]$IncludeFinanceReportSmoke,
    [switch]$IncludeFormulaSmoke,
    [switch]$RequireLiveQuote,
    [switch]$AllowWebSocketSubscriptionChange,
    [switch]$AllowTqUninitialized,
    [switch]$AllowTdxHttpUnavailable
)

# Optional deployment-side runtime checks:
#   .\scripts\run-runtime-checks.ps1 -RunDatasourceInstall      # calls deploy_windows.ps1 -Only install
#   .\scripts\run-runtime-checks.ps1 -RunDatasourceStartupTest  # calls deploy_windows.ps1 -Only test

$ErrorActionPreference = "Stop"

if (-not $DatasourceDir) {
    $DatasourceDir = $PSScriptRoot | Split-Path -Parent
}
$DatasourceDir = [System.IO.Path]::GetFullPath($DatasourceDir)

if (-not $ApplianceRoot) {
    $candidateRoot = Split-Path $DatasourceDir -Parent
    if (Test-Path (Join-Path $candidateRoot "health-check.ps1") -PathType Leaf) {
        $ApplianceRoot = $candidateRoot
    }
}
if ($ApplianceRoot) {
    $ApplianceRoot = [System.IO.Path]::GetFullPath($ApplianceRoot)
}

if (-not $EnvFile) {
    $EnvFile = Join-Path $DatasourceDir ".env"
}

$BaseUrl = $BaseUrl.TrimEnd("/")
if (-not $WsUrl) {
    $httpBase = $BaseUrl -replace "^http://", "ws://" -replace "^https://", "wss://"
    $WsUrl = "$httpBase/ws/quote/$ClientId"
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "===== $Message =====" -ForegroundColor Cyan
}

function Write-Ok {
    param([string]$Message)
    Write-Host "  [OK] $Message" -ForegroundColor Green
}

function Write-Warn {
    param([string]$Message)
    Write-Host "  [WARN] $Message" -ForegroundColor Yellow
}

function Write-Fail {
    param([string]$Message)
    Write-Host "  [FAIL] $Message" -ForegroundColor Red
}

function ConvertTo-TdxHttpSymbol {
    param([string]$Symbol)

    $normalized = $Symbol.Trim().ToUpperInvariant()
    if ($normalized -match "^(?<code>\d{6})\.(?<market>SH|SZ)$") {
        return "$($Matches.code).$($Matches.market)"
    }
    if ($normalized -match "^(?<market>SH|SZ)(?<code>\d{6})$") {
        return "$($Matches.code).$($Matches.market)"
    }
    return $normalized
}

function Get-CurrentPowerShellExe {
    $path = [System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName
    if ($path -and (Test-Path $path -PathType Leaf)) {
        return $path
    }
    return "pwsh"
}

function Invoke-RuntimeStep {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Step $Name
    try {
        & $Action
        Write-Ok "$Name passed"
    }
    catch {
        Write-Fail "$Name failed: $_"
        throw
    }
}

function Invoke-ChildScript {
    param(
        [string]$ScriptPath,
        [string[]]$Arguments = @(),
        [switch]$Required
    )

    if (-not (Test-Path $ScriptPath -PathType Leaf)) {
        if ($Required) {
            throw "Required script not found: $ScriptPath"
        }
        Write-Warn "Script not found, skipped: $ScriptPath"
        return
    }

    $shell = Get-CurrentPowerShellExe
    Write-Host "  $shell -NoProfile -File $ScriptPath $($Arguments -join ' ')" -ForegroundColor DarkGray
    & $shell -NoProfile -File $ScriptPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$ScriptPath failed with exit code $LASTEXITCODE"
    }
}

function Get-MissingSourceSelfTestFiles {
    param(
        [string]$RootDir,
        [string]$SelfTestPath
    )

    $requiredFiles = @(
        (Join-Path $RootDir ".env.windows.example"),
        $SelfTestPath
    )
    $missing = @()
    foreach ($file in $requiredFiles) {
        if (-not (Test-Path $file -PathType Leaf)) {
            $missing += $file
        }
    }
    return $missing
}

function Get-TdxServiceLogPath {
    if ($ApplianceRoot) {
        return Join-Path $ApplianceRoot "datasource\logs\mist-tdx-datasource"
    }
    return Join-Path $DatasourceDir "logs\mist-tdx-datasource"
}

function Get-WindowsServiceState {
    param([string]$Name)

    if ([System.Environment]::OSVersion.Platform -ne "Win32NT") {
        return [pscustomobject]@{
            IsWindows = $false
            Exists = $false
            Status = "not-windows"
            Name = $Name
        }
    }

    $service = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $service) {
        return [pscustomobject]@{
            IsWindows = $true
            Exists = $false
            Status = "missing"
            Name = $Name
        }
    }

    return [pscustomobject]@{
        IsWindows = $true
        Exists = $true
        Status = [string]$service.Status
        Name = $Name
    }
}

function Write-TdxRuntimeDiagnostics {
    param([object]$ServiceState)

    $logPath = Get-TdxServiceLogPath
    if ($ServiceState.IsWindows) {
        if (-not $ServiceState.Exists) {
            Write-Warn "Windows service '$($ServiceState.Name)' was not found."
            Write-Warn "Install it with scripts\winsw\install-tdx-datasource.ps1 after TDX is logged in."
        }
        elseif ($ServiceState.Status -ne "Running") {
            Write-Warn "Windows service '$($ServiceState.Name)' status is $($ServiceState.Status), not Running."
            Write-Warn "Start it with: Start-Service -Name $($ServiceState.Name)"
        }
        else {
            Write-Warn "Windows service '$($ServiceState.Name)' is Running but $BaseUrl/health did not respond."
        }
    }
    else {
        Write-Warn "Skipping Windows service status check on this platform."
    }

    Write-Warn "Check TDX terminal login/connection and clear conflicting strategy entries before restarting."
    Write-Warn "Check datasource logs under: $logPath"
}

function Invoke-TdxHealthRequest {
    try {
        return Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec $TimeoutSeconds
    }
    catch {
        $serviceState = Get-WindowsServiceState -Name $TdxServiceName
        Write-TdxRuntimeDiagnostics -ServiceState $serviceState
        throw "TDX datasource HTTP is not reachable at $BaseUrl/health. Original error: $_"
    }
}

function Assert-PropertyExists {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object -or -not ($Object.PSObject.Properties.Name -contains $Name)) {
        throw "Expected property '$Name' was not present."
    }
}

function Get-ObjectProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($property) {
        return $property.Value
    }
    return $null
}

function Get-NativeProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object) {
        return $null
    }
    $expected = $Name.Replace("_", "").ToLowerInvariant()
    foreach ($property in $Object.PSObject.Properties) {
        $token = $property.Name.Replace("_", "").ToLowerInvariant()
        if ($token -eq $expected) {
            return $property.Value
        }
    }
    return $null
}

function Assert-EnvelopeOk {
    param(
        [object]$Envelope,
        [string]$Name
    )

    Assert-PropertyExists -Object $Envelope -Name "ok"
    if ($Envelope.ok -ne $true) {
        $errorText = ""
        if ($Envelope.PSObject.Properties.Name -contains "error") {
            $errorText = $Envelope.error | ConvertTo-Json -Compress -Depth 8
        }
        throw "$Name returned ok=false. $errorText"
    }
}

function Assert-ArrayNotEmpty {
    param(
        [object]$Value,
        [string]$Name
    )

    if ($null -eq $Value -or $Value.Count -lt 1) {
        throw "$Name must be a non-empty array."
    }
}

function Assert-ValuePresent {
    param(
        [object]$Value,
        [string]$Name
    )

    if ($null -eq $Value) {
        throw "$Name must be present."
    }
}

function Assert-NumericProperty {
    param(
        [object]$Object,
        [string]$Name
    )

    Assert-PropertyExists -Object $Object -Name $Name
    $number = 0.0
    if (-not [double]::TryParse([string](Get-ObjectProperty -Object $Object -Name $Name), [ref]$number)) {
        throw "Expected property '$Name' to be numeric."
    }
}

function Get-RawMarketDataContainers {
    param(
        [object]$Result,
        [string]$Symbol
    )

    $fields = @("Open", "High", "Low", "Close", "Volume", "Amount")
    $containers = @()
    if ($null -ne $Result) {
        $containers += $Result
    }

    $value = Get-NativeProperty -Object $Result -Name "Value"
    if ($null -ne $value) {
        $containers += $value
    }

    # Raw get_market_data direct result shapes vary by TDX bridge version:
    # some wrap rows under Value, some under the symbol, and some return field tables directly.
    foreach ($container in @($containers)) {
        $symbolData = Get-ObjectProperty -Object $container -Name $Symbol
        if ($null -ne $symbolData) {
            $containers += $symbolData
            continue
        }

        if ($null -ne $container -and $container.PSObject.Properties.Count -gt 0) {
            $firstProperty = $container.PSObject.Properties[0]
            if ($fields -notcontains $firstProperty.Name) {
                $containers += $firstProperty.Value
            }
        }
    }

    return $containers
}

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Payload
    )

    $body = $Payload | ConvertTo-Json -Depth 12 -Compress
    return Invoke-RestMethod `
        -Method Post `
        -Uri $Uri `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec $TimeoutSeconds
}

function Assert-RawMarketDataResult {
    param(
        [object]$Result,
        [string]$Symbol
    )

    $containers = @(Get-RawMarketDataContainers -Result $Result -Symbol $Symbol)

    foreach ($field in @("Open", "High", "Low", "Close", "Volume", "Amount")) {
        $series = $null
        foreach ($container in $containers) {
            $candidate = Get-NativeProperty -Object $container -Name $field
            if ($null -ne $candidate) {
                $series = $candidate
                break
            }
        }
        if ($null -eq $series) {
            throw "Raw get_market_data result is missing field $field. Accepted shapes: Value wrapper, symbol wrapper, or Raw get_market_data direct result."
        }
        Assert-ArrayNotEmpty -Value $series -Name "Raw get_market_data field $field"
    }
}

function Assert-RawSnapshotResult {
    param([object]$Result)

    foreach ($field in @("Now", "LastClose", "Open", "Max", "Min", "Volume", "Amount", "ErrorId")) {
        $value = Get-NativeProperty -Object $Result -Name $field
        if ($null -eq $value) {
            throw "Raw get_market_snapshot result is missing $field."
        }
    }
}

function Assert-RawGpOneDataResult {
    param(
        [object]$Result,
        [string]$Symbol,
        [string]$Field
    )

    $containers = @()
    if ($null -ne $Result) {
        $containers += $Result
    }

    $value = Get-NativeProperty -Object $Result -Name "Value"
    if ($null -ne $value) {
        $containers += $value
    }

    foreach ($container in @($containers)) {
        $fieldData = Get-NativeProperty -Object $container -Name $Field
        if ($null -ne $fieldData) {
            $symbolValue = Get-ObjectProperty -Object $fieldData -Name $Symbol
            if ($null -ne $symbolValue) {
                return
            }
            if ($fieldData.PSObject.Properties.Count -gt 0) {
                return
            }
        }

        $symbolData = Get-ObjectProperty -Object $container -Name $Symbol
        if ($null -ne $symbolData) {
            $fieldValue = Get-NativeProperty -Object $symbolData -Name $Field
            if ($null -ne $fieldValue) {
                return
            }
        }
    }

    throw "Raw get_gp_one_data result is missing field '$Field' for symbol '$Symbol'."
}

function Test-HealthEndpoint {
    $health = Invoke-TdxHealthRequest
    foreach ($key in @("status", "instance", "adapter", "tdxHttpReachable", "tqInitialized", "collectorState")) {
        Assert-PropertyExists -Object $health -Name $key
    }
    if (($health.tqInitialized -ne $true) -and (-not $AllowTqUninitialized)) {
        throw "TDX service is not initialized."
    }
    if (($health.tdxHttpReachable -ne $true) -and (-not $AllowTdxHttpUnavailable)) {
        throw "TDX native HTTP is not reachable. Pass -AllowTdxHttpUnavailable to downgrade this check."
    }
}

function Test-ProviderManifest {
    $providers = Invoke-RestMethod -Method Get -Uri "$BaseUrl/providers" -TimeoutSec $TimeoutSeconds
    Assert-EnvelopeOk -Envelope $providers -Name "provider manifest"
    Assert-ArrayNotEmpty -Value $providers.data.providers -Name "providers"

    $providerIds = @($providers.data.providers | ForEach-Object { $_.id })
    foreach ($providerId in @("tdx")) {
        if ($providerIds -notcontains $providerId) {
            throw "Provider manifest is missing provider '$providerId'."
        }
    }
    if ($providerIds -contains "qmt") {
        throw "TDX provider manifest must not include provider 'qmt'. Use QMT service :9002 for QMT bars."
    }

    foreach ($provider in $providers.data.providers) {
        Assert-ArrayNotEmpty -Value $provider.capabilities -Name "$($provider.id) capabilities"
    }
}

function Test-BasicTdxSmoke {
    Test-HealthEndpoint
    Test-ProviderManifest

    $rawBars = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/raw/tdx/call" `
        -Payload @{
            method = "get_market_data"
            params = @{
                stock_list = @($RawSymbol)
                period = $Period
                count = $Count
                dividend_type = "none"
            }
        }
    Assert-EnvelopeOk -Envelope $rawBars -Name "raw get_market_data"
    Assert-RawMarketDataResult -Result $rawBars.data.result -Symbol $RawSymbol

    $bars = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/bars/query" `
        -Payload @{ symbols = @($Symbol); period = $Period; count = $Count }
    Assert-EnvelopeOk -Envelope $bars -Name "normalized bars query"
    Assert-ArrayNotEmpty -Value $bars.data.bars -Name "normalized bars"
    foreach ($field in @("open", "high", "low", "close", "volume", "amount")) {
        Assert-NumericProperty -Object $bars.data.bars[0] -Name $field
    }

    $rawSnapshot = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/raw/tdx/call" `
        -Payload @{
            method = "get_market_snapshot"
            params = @{
                stock_code = $RawSymbol
                field_list = @()
            }
        }
    Assert-EnvelopeOk -Envelope $rawSnapshot -Name "raw get_market_snapshot"
    Assert-RawSnapshotResult -Result $rawSnapshot.data.result

    $snapshots = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/snapshots/query" `
        -Payload @{ symbols = @($Symbol) }
    Assert-EnvelopeOk -Envelope $snapshots -Name "normalized snapshots query"
    Assert-ArrayNotEmpty -Value $snapshots.data.snapshots -Name "normalized snapshots"
    foreach ($field in @("last", "open", "high", "low", "lastClose", "volume", "amount", "asOf")) {
        Assert-PropertyExists -Object $snapshots.data.snapshots[0] -Name $field
    }

    $sectors = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/sectors/query" `
        -Payload @{ sector = $Sector }
    Assert-EnvelopeOk -Envelope $sectors -Name "sector query"
    Assert-ArrayNotEmpty -Value $sectors.data.symbols -Name "sector symbols"

    $sectorList = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/sectors/list/query" `
        -Payload @{ listType = 1 }
    Assert-EnvelopeOk -Envelope $sectorList -Name "sector list query"
    Assert-ArrayNotEmpty -Value $sectorList.data.sectors -Name "sector list"

    $tradingDates = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/calendar/trading-dates/query" `
        -Payload @{ market = "SH"; count = $Count }
    Assert-EnvelopeOk -Envelope $tradingDates -Name "trading dates query"
    Assert-ArrayNotEmpty -Value $tradingDates.data.tradingDates -Name "trading dates"

    $securities = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/securities/query" `
        -Payload @{ market = "5" }
    Assert-EnvelopeOk -Envelope $securities -Name "securities query"
    Assert-ArrayNotEmpty -Value $securities.data.securities -Name "securities"

    $securityInfo = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/securities/info/query" `
        -Payload @{ symbols = @($Symbol) }
    Assert-EnvelopeOk -Envelope $securityInfo -Name "security info query"
    Assert-ArrayNotEmpty -Value $securityInfo.data.securities -Name "security info"

    $priceVolume = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/price-volume/query" `
        -Payload @{ symbols = @($Symbol); fields = @("price", "volume", "amount") }
    Assert-EnvelopeOk -Envelope $priceVolume -Name "price-volume query"
    Assert-ArrayNotEmpty -Value $priceVolume.data.items -Name "price-volume items"
}

function Test-FinanceReportSmoke {
    $rawFinance = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/raw/tdx/call" `
        -Payload @{
            method = "get_gp_one_data"
            params = @{
                stock_list = @($RawSymbol)
                table_list = @($FinanceField)
            }
        }
    Assert-EnvelopeOk -Envelope $rawFinance -Name "raw get_gp_one_data"
    Assert-RawGpOneDataResult -Result $rawFinance.data.result -Symbol $RawSymbol -Field $FinanceField

    $financialData = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/finance/financial-data/query" `
        -Payload @{
            symbols = @($Symbol)
            fields = @($FinancialDataField)
            startTime = "20250101"
            endTime = "20251231"
            reportType = "tag_time"
        }
    Assert-EnvelopeOk -Envelope $financialData -Name "financial data query"
    Assert-PropertyExists -Object $financialData.data -Name "items"

    $financialDataByDate = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/finance/financial-data/by-date/query" `
        -Payload @{ symbols = @($Symbol); fields = @($FinancialDataByDateField); year = 0; mmdd = 0 }
    Assert-EnvelopeOk -Envelope $financialDataByDate -Name "financial data by date query"
    Assert-PropertyExists -Object $financialDataByDate.data -Name "items"

    $finance = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/finance/single-data/query" `
        -Payload @{ symbols = @($Symbol); fields = @($FinanceField) }
    Assert-EnvelopeOk -Envelope $finance -Name "single finance data query"
    Assert-ArrayNotEmpty -Value $finance.data.items -Name "single finance data items"
    foreach ($field in @("symbol", "field", "value")) {
        Assert-PropertyExists -Object $finance.data.items[0] -Name $field
    }

    $stockTrade = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reports/stock-trade/query" `
        -Payload @{
            symbols = @($Symbol)
            fields = @($StockTradeField)
            startTime = "20250101"
            endTime = "20250102"
        }
    Assert-EnvelopeOk -Envelope $stockTrade -Name "stock trade aggregate query"
    Assert-PropertyExists -Object $stockTrade.data -Name "items"

    $stockTradeByDate = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reports/stock-trade/by-date/query" `
        -Payload @{ symbols = @($Symbol); fields = @($StockTradeByDateField); year = 0; mmdd = 0 }
    Assert-EnvelopeOk -Envelope $stockTradeByDate -Name "stock trade aggregate by date query"
    Assert-PropertyExists -Object $stockTradeByDate.data -Name "items"

    $sectorTrade = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reports/sector-trade/query" `
        -Payload @{
            sectorCodes = @($SectorTradeCode)
            fields = @($SectorTradeField)
            startTime = "20250101"
            endTime = "20250102"
        }
    Assert-EnvelopeOk -Envelope $sectorTrade -Name "sector trade aggregate query"
    Assert-PropertyExists -Object $sectorTrade.data -Name "items"

    $sectorTradeByDate = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reports/sector-trade/by-date/query" `
        -Payload @{ sectorCodes = @($SectorTradeCode); fields = @($SectorTradeByDateField); year = 0; mmdd = 0 }
    Assert-EnvelopeOk -Envelope $sectorTradeByDate -Name "sector trade aggregate by date query"
    Assert-PropertyExists -Object $sectorTradeByDate.data -Name "items"

    $marketTrade = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reports/market-trade/query" `
        -Payload @{
            fields = @($MarketTradeField)
            startTime = "20250101"
            endTime = "20250102"
        }
    Assert-EnvelopeOk -Envelope $marketTrade -Name "market trade aggregate query"
    Assert-PropertyExists -Object $marketTrade.data -Name "items"

    $marketTradeByDate = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reports/market-trade/by-date/query" `
        -Payload @{ fields = @($MarketTradeByDateField); year = 0; mmdd = 0 }
    Assert-EnvelopeOk -Envelope $marketTradeByDate -Name "market trade aggregate by date query"
    Assert-PropertyExists -Object $marketTradeByDate.data -Name "items"

}

function Test-ReferenceInstrumentSmoke {
    $relations = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reference/relations/query" `
        -Payload @{ symbol = $Symbol }
    Assert-EnvelopeOk -Envelope $relations -Name "relations query"
    Assert-PropertyExists -Object $relations.data -Name "relations"

    $ipo = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reference/ipo/query" `
        -Payload @{ ipoType = 0; ipoDate = 0 }
    Assert-EnvelopeOk -Envelope $ipo -Name "IPO query"
    Assert-PropertyExists -Object $ipo.data -Name "items"

    $rawShareCapital = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/raw/tdx/call" `
        -Payload @{
            method = "get_gb_info"
            params = @{
                stock_code = $RawSymbol
                date_list = @()
                count = 1
            }
        }
    Assert-EnvelopeOk -Envelope $rawShareCapital -Name "raw get_gb_info"
    Assert-ValuePresent -Value $rawShareCapital.data.result -Name "raw get_gb_info result"

    $shareCapital = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reference/share-capital/query" `
        -Payload @{ symbol = $Symbol; count = 1 }
    Assert-EnvelopeOk -Envelope $shareCapital -Name "share-capital query"
    Assert-ArrayNotEmpty -Value $shareCapital.data.items -Name "share-capital items"

    $dividendFactors = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/reference/dividend-factors/query" `
        -Payload @{ symbol = $Symbol }
    Assert-EnvelopeOk -Envelope $dividendFactors -Name "dividend factors query"
    Assert-PropertyExists -Object $dividendFactors.data -Name "items"

    $convertibleBonds = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/instruments/convertible-bonds/query" `
        -Payload @{
            symbol = $ConvertibleBondSymbol
            fields = @("KZZCode", "HSCode")
            nativeMethod = "get_kzz_info"
        }
    Assert-EnvelopeOk -Envelope $convertibleBonds -Name "convertible bonds query"
    Assert-PropertyExists -Object $convertibleBonds.data -Name "items"

    $trackingEtfs = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/instruments/tracking-etfs/query" `
        -Payload @{ indexSymbol = $TrackingEtfIndexSymbol }
    Assert-EnvelopeOk -Envelope $trackingEtfs -Name "tracking ETFs query"
    Assert-PropertyExists -Object $trackingEtfs.data -Name "items"
}

function Test-FormulaSmoke {
    $rawFormulaList = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/raw/tdx/call" `
        -Payload @{
            method = "formula_get_all"
            params = @{
                formula_type = 0
            }
        }
    Assert-EnvelopeOk -Envelope $rawFormulaList -Name "raw formula_get_all"
    Assert-ValuePresent -Value $rawFormulaList.data.result -Name "raw formula_get_all result"

    $formulaList = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/formulas/metadata/query" `
        -Payload @{ formulaType = 0 }
    Assert-EnvelopeOk -Envelope $formulaList -Name "formula metadata query"
    Assert-ArrayNotEmpty -Value $formulaList.data.items -Name "formula metadata items"
}

function Receive-WebSocketText {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [int]$TimeoutSeconds = 15
    )

    $cts = [System.Threading.CancellationTokenSource]::new()
    $cts.CancelAfter([TimeSpan]::FromSeconds($TimeoutSeconds))
    $buffer = [byte[]]::new(4096)
    $builder = [System.Text.StringBuilder]::new()

    try {
        do {
            $segment = [System.ArraySegment[byte]]::new($buffer)
            $result = $Socket.ReceiveAsync($segment, $cts.Token).GetAwaiter().GetResult()
            if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                throw "WebSocket closed before the expected message was received."
            }
            if ($result.Count -gt 0) {
                [void]$builder.Append([System.Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
            }
        } while (-not $result.EndOfMessage)
    }
    finally {
        $cts.Dispose()
    }

    return $builder.ToString()
}

function Send-WebSocketJson {
    param(
        [System.Net.WebSockets.ClientWebSocket]$Socket,
        [hashtable]$Payload
    )

    $json = $Payload | ConvertTo-Json -Depth 12 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $segment = [System.ArraySegment[byte]]::new($bytes)
    [void]$Socket.SendAsync(
        $segment,
        [System.Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        [System.Threading.CancellationToken]::None
    ).GetAwaiter().GetResult()
}

function Test-WebSocketSmoke {
    $socket = [System.Net.WebSockets.ClientWebSocket]::new()
    try {
        $connectCts = [System.Threading.CancellationTokenSource]::new()
        $connectCts.CancelAfter([TimeSpan]::FromSeconds($TimeoutSeconds))
        [void]$socket.ConnectAsync([Uri]$WsUrl, $connectCts.Token).GetAwaiter().GetResult()
        $connectCts.Dispose()

        $ready = Receive-WebSocketText -Socket $socket -TimeoutSeconds $TimeoutSeconds | ConvertFrom-Json
        if ($ready.type -ne "ready") {
            throw "Expected WebSocket ready message, got: $($ready | ConvertTo-Json -Compress -Depth 8)"
        }

        Send-WebSocketJson -Socket $socket -Payload @{
            "type" = "ping"
        }

        $pong = Receive-WebSocketText -Socket $socket -TimeoutSeconds $TimeoutSeconds | ConvertFrom-Json
        if ($pong.type -ne "pong") {
            throw "Expected WebSocket pong message, got: $($pong | ConvertTo-Json -Compress -Depth 8)"
        }

        if ($RequireLiveQuote) {
            if (-not $AllowWebSocketSubscriptionChange) {
                throw "RequireLiveQuote needs -AllowWebSocketSubscriptionChange because it changes TDX subscriptions. Do not use it while Mist backend owns the TDX subscription leader."
            }

            Send-WebSocketJson -Socket $socket -Payload @{
                "type" = "sync_subscriptions"
                "symbols" = @($Symbol)
            }

            $subscribed = Receive-WebSocketText -Socket $socket -TimeoutSeconds $TimeoutSeconds | ConvertFrom-Json
            if ($subscribed.type -ne "subscribed") {
                throw "Expected WebSocket subscribed message, got: $($subscribed | ConvertTo-Json -Compress -Depth 8)"
            }

            $deadline = (Get-Date).AddSeconds($LiveQuoteTimeoutSeconds)
            $quoteSeen = $false
            while ((Get-Date) -lt $deadline) {
                $remaining = [Math]::Max(1, [int]($deadline - (Get-Date)).TotalSeconds)
                $message = Receive-WebSocketText -Socket $socket -TimeoutSeconds $remaining | ConvertFrom-Json
                if ($message.type -eq "quote") {
                    Assert-PropertyExists -Object $message -Name "data"
                    Assert-PropertyExists -Object $message.data -Name "snapshot"
                    Assert-PropertyExists -Object $message.data.snapshot -Name "Code"
                    Assert-PropertyExists -Object $message.data.snapshot -Name "Now"
                    $quoteSeen = $true
                    break
                }
            }
            if (-not $quoteSeen) {
                throw "No live quote event arrived within $LiveQuoteTimeoutSeconds seconds."
            }

            Send-WebSocketJson -Socket $socket -Payload @{
                "type" = "unsubscribe"
                "stocks" = @($Symbol)
            }

            $unsubscribed = Receive-WebSocketText -Socket $socket -TimeoutSeconds $TimeoutSeconds | ConvertFrom-Json
            if ($unsubscribed.type -ne "unsubscribed") {
                throw "Expected WebSocket unsubscribed message, got: $($unsubscribed | ConvertTo-Json -Compress -Depth 8)"
            }
        }
    }
    finally {
        if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            [void]$socket.CloseAsync(
                [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                "runtime checks complete",
                [System.Threading.CancellationToken]::None
            ).GetAwaiter().GetResult()
        }
        $socket.Dispose()
    }
}

if (-not $RawSymbol) {
    $RawSymbol = ConvertTo-TdxHttpSymbol -Symbol $Symbol
}

Write-Host "Mist datasource runtime checks" -ForegroundColor Cyan
Write-Host "  DatasourceDir: $DatasourceDir"
Write-Host "  ApplianceRoot: $ApplianceRoot"
Write-Host "  BaseUrl:       $BaseUrl"
Write-Host "  WsUrl:         $WsUrl"
Write-Host "  Symbol:        $Symbol"
Write-Host "  RawSymbol:     $RawSymbol"
Write-Host "  Sector:        $Sector"
Write-Host "  SectorTrade:   $SectorTradeCode"
Write-Host "  FinanceField:  $FinanceField"

$selfTestScript = Join-Path $DatasourceDir "scripts\test_windows_scripts.ps1"
$preflightScript = Join-Path $DatasourceDir "scripts\preflight-sdk.ps1"
$deployScript = Join-Path $DatasourceDir "scripts\deploy_windows.ps1"
$winswProbeScript = Join-Path $DatasourceDir "scripts\winsw\test-tdx-datasource.ps1"
$applianceHealthScript = if ($ApplianceRoot) { Join-Path $ApplianceRoot "health-check.ps1" } else { "" }

try {
    if (-not $SkipScriptSelfTest) {
        $missingSourceSelfTestFiles = @(Get-MissingSourceSelfTestFiles -RootDir $DatasourceDir -SelfTestPath $selfTestScript)
        if ($missingSourceSelfTestFiles.Count -eq 0) {
            Invoke-RuntimeStep "Datasource script self-test" {
                Invoke-ChildScript -ScriptPath $selfTestScript -Required
            }
        }
        elseif ($RequireScriptSelfTest) {
            throw "Datasource script self-test requires source-tree files that are missing from this runtime package: $($missingSourceSelfTestFiles -join ', ')"
        }
        else {
            Write-Step "Datasource script self-test"
            Write-Warn "Skipped source-tree self-test because this runtime package is missing: $($missingSourceSelfTestFiles -join ', ')"
            Write-Warn "Pass -RequireScriptSelfTest to fail instead."
        }
    }

    if (-not $SkipSdkPreflight) {
        Invoke-RuntimeStep "Datasource SDK preflight" {
            Invoke-ChildScript -ScriptPath $preflightScript -Arguments @("-EnvFile", $EnvFile) -Required
        }
    }

    if ($RunDatasourceInstall) {
        Invoke-RuntimeStep "Datasource install check" {
            Invoke-ChildScript -ScriptPath $deployScript -Arguments @("-Only", "install") -Required
        }
    }

    if ($RunDatasourceStartupTest) {
        Invoke-RuntimeStep "Datasource temporary startup check" {
            Invoke-ChildScript -ScriptPath $deployScript -Arguments @("-Only", "test") -Required
        }
    }

    if (-not $SkipWinSWProbe) {
        Invoke-RuntimeStep "TDX WinSW runtime probe" {
            [void](Invoke-TdxHealthRequest)
            $winswProbeArgs = @("-BaseUrl", $BaseUrl, "-WsUrl", $WsUrl, "-Symbol", $Symbol)
            if ($SkipWebSocket) {
                $winswProbeArgs += "-SkipWebSocket"
            }
            Invoke-ChildScript `
                -ScriptPath $winswProbeScript `
                -Arguments $winswProbeArgs `
                -Required
        }
    }

    if (-not $SkipApplianceHealth) {
        Invoke-RuntimeStep "Appliance health check" {
            if (-not $applianceHealthScript) {
                Write-Warn "Appliance root was not resolved; appliance health check skipped."
                return
            }
            $healthArgs = @()
            if (-not $SkipMySQL) {
                $healthArgs += "-IncludeMySQL"
            }
            Invoke-ChildScript -ScriptPath $applianceHealthScript -Arguments $healthArgs
        }
    }

    if (-not $SkipSmoke) {
        Invoke-RuntimeStep "TDX basic HTTP smoke" {
            Test-BasicTdxSmoke
        }
    }

    if ($IncludeReferenceInstrumentSmoke) {
        Invoke-RuntimeStep "TDX reference/instrument HTTP smoke" {
            Test-ReferenceInstrumentSmoke
        }
    }

    if ($IncludeFinanceReportSmoke) {
        Invoke-RuntimeStep "TDX finance/report HTTP smoke" {
            Test-FinanceReportSmoke
        }
    }

    if ($IncludeFormulaSmoke) {
        Invoke-RuntimeStep "TDX formula HTTP smoke" {
            Test-FormulaSmoke
        }
    }

    if (-not $SkipWebSocket) {
        Invoke-RuntimeStep "TDX WebSocket smoke" {
            Test-WebSocketSmoke
        }
    }
}
catch {
    Write-Fail "Runtime checks failed."
    exit 1
}

Write-Host ""
Write-Host "All selected runtime checks passed." -ForegroundColor Green
