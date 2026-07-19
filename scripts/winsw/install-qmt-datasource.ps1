[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$ProjectDir = "",
    [string]$ServiceDir = "",
    [string]$WinSWExe = "",
    [string]$Executable = "",
    [string]$Arguments = "run uvicorn qmt.main:app --host %QMT_HOST% --port %QMT_PORT%",
    [string]$QmtHost = "127.0.0.1",
    [int]$DatasourcePort = 9002,
    [string]$QmtBridgeGatewayUrl = "http://127.0.0.1:9002/qmt/bridge"
)

$ErrorActionPreference = "Stop"
$ServiceName = "mist-qmt-datasource"
$ScriptDir = $PSScriptRoot
$CommonScript = Join-Path (Split-Path -Parent $ScriptDir) "windows-common.ps1"
. $CommonScript

function Get-ConfiguredValue {
    param(
        [string]$Content,
        [string]$Name,
        [object]$Default
    )

    $fromFile = ""
    if ($Content) {
        $fromFile = Get-EnvValue -Content $Content -Name $Name
    }
    if ($fromFile) { return $fromFile }

    $fromEnv = [System.Environment]::GetEnvironmentVariable($Name)
    if ($fromEnv) { return $fromEnv }

    return $Default
}

function Get-WindowsServiceController {
    param([string]$Name)

    if ([System.Environment]::OSVersion.Platform -ne "Win32NT") {
        return $null
    }

    return Get-Service -Name $Name -ErrorAction SilentlyContinue
}

function Invoke-WinSWCommand {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [switch]$AllowFailure
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $Exe @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if (($exitCode -ne 0) -and (-not $AllowFailure)) {
        throw "WinSW $($Arguments -join ' ') failed with exit code $exitCode. $output"
    }

    return @{
        ExitCode = $exitCode
        Output = "$output".Trim()
    }
}

function Set-TemplateValues {
    param(
        [string]$Template,
        [hashtable]$Values
    )

    $result = $Template
    foreach ($key in $Values.Keys) {
        $result = $result.Replace($key, [string]$Values[$key])
    }
    return $result
}

if (-not $ProjectDir) {
    $ProjectDir = Resolve-FullPath (Join-Path $ScriptDir "..\..")
}
else {
    $ProjectDir = Resolve-FullPath $ProjectDir
}

if (-not $ServiceDir) {
    $ServiceDir = Join-Path $ProjectDir "services\mist-qmt-datasource"
}
$ServiceDir = Resolve-FullPath $ServiceDir
$LogsDir = Resolve-FullPath (Join-Path $ProjectDir "logs\mist-qmt-datasource")
$TemplateFile = Join-Path $ScriptDir "mist-qmt-datasource.xml"
$ServiceExe = Join-Path $ServiceDir "$ServiceName.exe"
$ServiceXml = Join-Path $ServiceDir "$ServiceName.xml"

if (-not (Test-Path $TemplateFile -PathType Leaf)) {
    Write-Fail "Missing WinSW XML template: $TemplateFile"
    exit 1
}

$EnvFile = Join-Path $ProjectDir ".env"
$EnvContent = ""
if (Test-Path $EnvFile -PathType Leaf) {
    $EnvContent = Get-Content $EnvFile -Raw
}

if (-not $Executable) {
    $Executable = Resolve-UvExe -ProjectDir $ProjectDir -PreferPathLookup:$false
    if (-not $Executable) {
        $Executable = Resolve-UvExe -ProjectDir $ProjectDir -PreferPathLookup:$true
    }
    if (-not $Executable) {
        if ($WhatIfPreference) {
            Write-Warn "uv executable was not found. A real install requires runtime\uv.exe or uv on PATH."
        }
        else {
            Write-Fail "uv executable not found. Place uv.exe under runtime\ or pass -Executable."
            exit 1
        }
    }
}
if ($Executable) {
    Write-Ok "Datasource executable: $Executable"
}

if (-not $PSBoundParameters.ContainsKey("QmtHost")) {
    $QmtHost = Get-ConfiguredValue -Content $EnvContent -Name "QMT_HOST" -Default $QmtHost
}
if (-not $PSBoundParameters.ContainsKey("DatasourcePort")) {
    $DatasourcePort = [int](Get-ConfiguredValue -Content $EnvContent -Name "QMT_PORT" -Default $DatasourcePort)
}
if (-not $PSBoundParameters.ContainsKey("QmtBridgeGatewayUrl")) {
    $QmtBridgeGatewayUrl = Get-ConfiguredValue -Content $EnvContent -Name "QMT_BRIDGE_GATEWAY_URL" -Default $QmtBridgeGatewayUrl
}
$ResolvedWinSWExe = Resolve-WinSWExe -ProjectDir $ProjectDir -WinSWExe $WinSWExe
if (-not $ResolvedWinSWExe) {
    if ($WhatIfPreference) {
        Write-Warn "WinSW executable was not found. A real install requires -WinSWExe or a bundled winsw.exe."
    }
    else {
        Write-Fail "WinSW executable not found. Pass -WinSWExe or place winsw.exe under winsw\, tools\winsw\, or runtime\."
        exit 1
    }
}
else {
    Write-Ok "WinSW: $ResolvedWinSWExe"
}

Write-Warn "QMT strategy scripts are not loaded, registered, or deleted by this installer."
Write-Warn "Use the full QMT client UI to manual load/register/delete the bridge strategy when needed."

$ExistingService = Get-WindowsServiceController -Name $ServiceName
$ServiceExists = $null -ne $ExistingService

if ($ServiceExists) {
    Write-Step "Stop existing $ServiceName before updating service files"
    if ($ExistingService.Status -eq "Stopped") {
        Write-Ok "$ServiceName is already stopped"
    }
    elseif ($PSCmdlet.ShouldProcess($ServiceName, "Stop service before replacing WinSW executable")) {
        Stop-Service -Name $ServiceName -Force -ErrorAction Stop
        $ExistingService.WaitForStatus(
            [System.ServiceProcess.ServiceControllerStatus]::Stopped,
            [TimeSpan]::FromSeconds(30)
        )
        Write-Ok "$ServiceName stopped for update"
    }
}

Write-Step "Prepare WinSW service files"
if ($PSCmdlet.ShouldProcess($ServiceDir, "Create service directory")) {
    New-Item -ItemType Directory -Force -Path $ServiceDir | Out-Null
}
if ($PSCmdlet.ShouldProcess($LogsDir, "Create log directory")) {
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
}
if ($ResolvedWinSWExe -and $PSCmdlet.ShouldProcess($ServiceExe, "Copy WinSW executable")) {
    Copy-Item -Path $ResolvedWinSWExe -Destination $ServiceExe -Force
}

$Template = Get-Content $TemplateFile -Raw
$RenderedXml = Set-TemplateValues `
    -Template $Template `
    -Values @{
        "{{PROJECT_DIR}}" = ConvertTo-XmlEscapedValue $ProjectDir
        "{{DATASOURCE_EXECUTABLE}}" = ConvertTo-XmlEscapedValue $Executable
        "{{DATASOURCE_ARGUMENTS}}" = ConvertTo-XmlEscapedValue $Arguments
        "{{QMT_HOST}}" = ConvertTo-XmlEscapedValue $QmtHost
        "{{QMT_PORT}}" = ConvertTo-XmlEscapedValue $DatasourcePort
        "{{QMT_BRIDGE_GATEWAY_URL}}" = ConvertTo-XmlEscapedValue $QmtBridgeGatewayUrl
        "{{LOG_DIR}}" = ConvertTo-XmlEscapedValue $LogsDir
    }

if ($PSCmdlet.ShouldProcess($ServiceXml, "Render WinSW XML")) {
    $RenderedXml | Set-Content -Path $ServiceXml -Encoding UTF8
}

Write-Step "Install or update $ServiceName"
if ($ServiceExists) {
    if ($PSCmdlet.ShouldProcess($ServiceName, "Reinstall WinSW service definition")) {
        Invoke-WinSWCommand -Exe $ServiceExe -Arguments @("uninstall") -AllowFailure | Out-Null
        Invoke-WinSWCommand -Exe $ServiceExe -Arguments @("install") | Out-Null
        Write-Ok "$ServiceName service reinstalled"
    }
}
else {
    if ($PSCmdlet.ShouldProcess($ServiceName, "Install WinSW service")) {
        Invoke-WinSWCommand -Exe $ServiceExe -Arguments @("install") | Out-Null
        Write-Ok "$ServiceName service installed"
    }
}

Write-Step "Start $ServiceName"
if ($PSCmdlet.ShouldProcess($ServiceName, "Start service")) {
    $StartResult = Invoke-WinSWCommand -Exe $ServiceExe -Arguments @("start") -AllowFailure
    if ($StartResult.ExitCode -eq 0) {
        Write-Ok "$ServiceName start requested"
    }
    elseif ($StartResult.Output -match "already|running|SERVICE_RUNNING|started successfully") {
        Write-Warn "$ServiceName start returned exit code $($StartResult.ExitCode), but WinSW output indicates the service is running"
    }
    else {
        throw "Unable to start $ServiceName. $($StartResult.Output)"
    }
}

Write-Ok "WinSW service files: $ServiceDir"
$global:LASTEXITCODE = 0
