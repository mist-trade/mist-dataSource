# mist-datasource Windows 部署脚本
# Current appliance installs TDX through WinSW. This script only installs
# dependencies and runs temporary startup checks.
# 用法: 以管理员身份打开 PowerShell, 然后:
#   cd D:\mist-datasource
#   .\scripts\deploy_windows.ps1
#
# 也可只运行特定步骤:
#   .\scripts\deploy_windows.ps1 -Only install     # 只运行 install 步骤
#   .\scripts\deploy_windows.ps1 -Only test        # 只运行 test 步骤

param(
    [string]$Only = ""
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot | Split-Path -Parent
$LogsDir = Join-Path $ProjectDir "logs"

. "$PSScriptRoot\windows-common.ps1"

# ---- 前置检查 ----
if ($Only -and $Only -notin @("install", "test")) {
    Write-Fail "Unknown step: $Only. Use: install, test"
    exit 1
}

# ============================================
# Step 1: 环境检查
# ============================================
if (-not $Only -or $Only -eq "install") {
    Write-Step "Step 1/4: 环境检查"

    # 检查 Python
    $pythonExe = $null
    try { $pythonExe = (Get-Command python -ErrorAction Stop).Source } catch {}
    if (-not $pythonExe) {
        try { $pythonExe = (Get-Command python3 -ErrorAction Stop).Source } catch {}
    }
    if (-not $pythonExe) {
        try { $pythonExe = (Get-Command py -ErrorAction Stop).Source } catch {}
    }
    if ($pythonExe) {
        $pyVer = & $pythonExe --version 2>&1
        Write-Ok "Python: $pyVer ($pythonExe)"
    } else {
        Write-Warn "Python is not on PATH; uv sync will create/find Python 3.12"
    }

    # 检查 uv
    $uvExe = Resolve-UvExe -ProjectDir $ProjectDir
    if (-not $uvExe) {
        Write-Fail "uv 未安装，且部署包内未找到 runtime\uv.exe。运行: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
        exit 1
    }
    $uvVer = & $uvExe --version 2>&1
    Write-Ok "uv: $uvVer ($uvExe)"

    # 检查 .env
    $envFile = Join-Path $ProjectDir ".env"
    if (-not (Test-Path $envFile)) {
        Write-Host "  .env 不存在, 从 .env.example 复制..." -ForegroundColor Yellow
        Copy-Item (Join-Path $ProjectDir ".env.example") $envFile
        Write-Host "  请编辑 .env 填写配置后重新运行此脚本" -ForegroundColor Yellow
        Write-Host "  必填项: APP_ENV=production, TDX_SDK_PATH=..." -ForegroundColor Yellow
        notepad $envFile
        exit 0
    }
    Write-Ok ".env 已存在"

    # 检查 .env 中的关键配置
    $envContent = Get-Content $envFile -Raw
    $appEnv = Get-EnvValue $envContent "APP_ENV"
    if ($appEnv -eq "production") {
        Write-Ok "APP_ENV=production (生产模式)"

        $preflight = Join-Path $PSScriptRoot "preflight-sdk.ps1"
        if (Test-Path $preflight -PathType Leaf) {
            & $preflight -EnvFile $envFile
        } else {
            Write-Warn "preflight-sdk.ps1 未找到, 跳过 SDK 布局检查"
        }
    } else {
        Write-Host "  [INFO] APP_ENV=$appEnv (开发模式, 使用 mock adapter)" -ForegroundColor Yellow
    }

}

# ============================================
# Step 2: 安装依赖
# ============================================
if (-not $Only -or $Only -eq "install") {
    Write-Step "Step 2/4: 安装依赖 (uv sync)"

    Push-Location $ProjectDir
    try {
        if (-not $uvExe) {
            $uvExe = Resolve-UvExe -ProjectDir $ProjectDir
        }
        if (-not $uvExe) {
            Write-Fail "uv 未安装，且部署包内未找到 runtime\uv.exe。运行: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
            exit 1
        }

        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        # 所有依赖都在主依赖列表中, 不需要 extra 参数
        $lockFile = Join-Path $ProjectDir "uv.lock"
        $syncArgs = if (Test-Path $lockFile -PathType Leaf) { @("sync", "--frozen") } else { @("sync") }
        if (-not $envContent) { $envContent = Get-Content (Join-Path $ProjectDir ".env") -Raw }
        $uvDefaultIndex = Get-EnvValue $envContent "UV_DEFAULT_INDEX"
        if (-not $uvDefaultIndex) { $uvDefaultIndex = $env:UV_DEFAULT_INDEX }
        if (-not $uvDefaultIndex) { $uvDefaultIndex = "https://pypi.tuna.tsinghua.edu.cn/simple" }
        $uvPython = Get-EnvValue $envContent "UV_PYTHON"
        if (-not $uvPython) { $uvPython = $env:UV_PYTHON }
        if (-not $uvPython) { $uvPython = "3.12" }
        $syncArgs += @("--python", $uvPython)
        $syncArgs += @("--default-index", $uvDefaultIndex)
        Write-Ok "uv python: $uvPython"
        Write-Ok "uv default index: $uvDefaultIndex"
        if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir | Out-Null }
        $uvSyncLog = Join-Path $LogsDir "uv-sync.log"
        Write-Host "  uv sync log: $uvSyncLog"
        try {
            & $uvExe @syncArgs *> $uvSyncLog
            $syncExit = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $prevEAP
        }
        if ($syncExit -ne 0) {
            Write-Fail "uv sync failed (exit code $syncExit)"
            Write-Host "`n===== Recent uv sync output =====" -ForegroundColor Yellow
            Get-Content $uvSyncLog -Tail 80 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
            exit $syncExit
        }
        Write-Ok "uv sync 完成"

        # 检查 venv 是否创建
        $venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Write-Fail ".venv 未创建, uv sync 可能失败了"
            exit 1
        }
        Write-Ok "venv Python: $venvPython"

        # 验证关键包
        & $venvPython -c "import fastapi; print(f'  fastapi {fastapi.__version__}')" 2>&1
        & $venvPython -c "import uvicorn; print(f'  uvicorn {uvicorn.__version__}')" 2>&1
    }
    finally {
        Pop-Location
    }
}

# ============================================
# Step 3: 测试启动
# ============================================
if (-not $Only -or $Only -eq "test") {
    Write-Step "Step 3/4: 测试 TDX 实例启动"

    $venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

    # 创建日志目录
    if (-not (Test-Path $LogsDir)) { New-Item -ItemType Directory -Path $LogsDir | Out-Null }

    # 读取 .env (确保 $envContent 可用)
    if (-not $envContent) { $envContent = Get-Content (Join-Path $ProjectDir ".env") -Raw }

    # 启动 TDX 实例
    $tdxTestLog = Join-Path $LogsDir "deploy-test-tdx.log"
    $tdxTestErr = Join-Path $LogsDir "deploy-test-tdx-err.log"
    Write-Host "  启动 TDX 实例 (临时, 仅测试)..."
    $proc = Start-Process -FilePath $venvPython `
        -ArgumentList "-m", "uvicorn", "tdx.main:app", "--host", "127.0.0.1", "--port", "9001" `
        -WorkingDirectory $ProjectDir `
        -RedirectStandardOutput $tdxTestLog `
        -RedirectStandardError $tdxTestErr `
        -PassThru -NoNewWindow

    # 等待启动, 最多重试 5 次 (SDK 加载 DLL 可能较慢)
    $tdxOk = $false
    Start-Sleep -Seconds 3
    if ($proc.HasExited) {
        Write-Fail "TDX 实例启动后立即退出 (exit code: $($proc.ExitCode))"
        Get-Content $tdxTestErr -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
    } else {
        $tdxOk = Wait-HttpHealth `
            -Name "TDX" `
            -Url "http://127.0.0.1:9001/health" `
            -Attempts 5 `
            -DelaySeconds 3 `
            -TimeoutSeconds 5
        if (-not $tdxOk) {
            Get-Content $tdxTestErr -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
            Get-Content $tdxTestLog -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
        }
        if (-not $proc.HasExited) {
            Stop-ProcessTreeBestEffort -Process $proc
        }
    }

    if (-not $tdxOk) {
        Write-Host "`n  TDX 测试失败! 请检查上面的错误信息。" -ForegroundColor Red
        Write-Host "  常见问题:" -ForegroundColor Yellow
        Write-Host "    1. APP_ENV=development -> 检查 mock adapter 是否正常" -ForegroundColor Yellow
        Write-Host "    2. APP_ENV=production -> 检查 TDX_SDK_PATH 是否正确, 通达信终端是否已登录" -ForegroundColor Yellow
        Write-Host "    3. 端口 9001 被占用 -> 关闭占用进程" -ForegroundColor Yellow
        if (-not $Only) {
            Write-Host "`n  是否继续测试 QMT? (Y/N)" -ForegroundColor Yellow
            $cont = Read-Host
            if ($cont -ne "Y") { exit 1 }
        }
    }

    Write-Step "Step 4/4: QMT bridge status"
    $qmtBridgeGatewayUrl = Get-EnvValue $envContent "QMT_BRIDGE_GATEWAY_URL"
    if ($qmtBridgeGatewayUrl) {
        Write-Host "  QMT bridge gateway configured: $qmtBridgeGatewayUrl" -ForegroundColor Yellow
        Write-Host "  QMT bridge is configured; use Windows full-QMT evidence before relying on live commands." -ForegroundColor Yellow
    } else {
        Write-Host "  QMT bridge gateway not configured; only local DAT paths can be tested." -ForegroundColor Yellow
    }
}

Write-Host "`n===== 部署完成 =====" -ForegroundColor Green
Write-Host "  日志目录: $LogsDir"
Write-Host "  说明: 此脚本只负责依赖安装和临时启动测试, 不再注册 Windows 服务。"
