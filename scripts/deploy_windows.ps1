# mist-datasource Windows 部署脚本
# 用法: 以管理员身份打开 PowerShell, 然后:
#   cd D:\mist-datasource
#   .\scripts\deploy_windows.ps1
#
# 也可只运行特定步骤:
#   .\scripts\deploy_windows.ps1 -SkipService      # 只测试, 不注册服务
#   .\scripts\deploy_windows.ps1 -Only install     # 只运行 install 步骤
#   .\scripts\deploy_windows.ps1 -Only test        # 只运行 test 步骤
#   .\scripts\deploy_windows.ps1 -Only service     # 只注册服务

param(
    [switch]$SkipService,
    [string]$Only = ""
)

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot | Split-Path -Parent
$LogsDir = Join-Path $ProjectDir "logs"

function Write-Step($msg) { Write-Host "`n===== $msg =====" -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Fail($msg) { Write-Host "  [FAIL] $msg" -ForegroundColor Red }

# ---- 前置检查 ----
if ($Only -and $Only -notin @("install", "test", "service")) {
    Write-Fail "Unknown step: $Only. Use: install, test, service"
    exit 1
}

# ============================================
# Step 1: 环境检查
# ============================================
if (-not $Only -or $Only -eq "install") {
    Write-Step "Step 1/5: 环境检查"

    # 检查 Python
    $pythonExe = $null
    try { $pythonExe = (Get-Command python -ErrorAction Stop).Source } catch {}
    if (-not $pythonExe) {
        try { $pythonExe = (Get-Command python3 -ErrorAction Stop).Source } catch {}
    }
    if (-not $pythonExe) {
        Write-Fail "Python 未安装。请安装 Python 3.12+ 并加入 PATH"
        exit 1
    }
    $pyVer = & $pythonExe --version 2>&1
    Write-Ok "Python: $pyVer ($pythonExe)"

    # 检查 uv
    $uvExe = $null
    try { $uvExe = (Get-Command uv -ErrorAction Stop).Source } catch {}
    if (-not $uvExe) {
        Write-Fail "uv 未安装。运行: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""
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
    $appEnv = if ($envContent -match 'APP_ENV\s*=\s*(\S+)') { $Matches[1] } else { "" }
    if ($appEnv -eq "production") {
        Write-Ok "APP_ENV=production (生产模式)"

        $tdxSdk = if ($envContent -match 'TDX_SDK_PATH\s*=\s*(.+)') { $Matches[1].Trim() } else { "" }
        if ($tdxSdk -and $tdxSdk -ne "") {
            if (Test-Path $tdxSdk) {
                Write-Ok "TDX_SDK_PATH=$tdxSdk (目录存在)"
            } else {
                Write-Fail "TDX_SDK_PATH=$tdxSdk 目录不存在!"
                exit 1
            }
        } else {
            Write-Host "  [WARN] TDX_SDK_PATH 未设置, TDX 实例将无法启动" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [INFO] APP_ENV=$appEnv (开发模式, 使用 mock adapter)" -ForegroundColor Yellow
    }

    # 检查 NSSM (仅注册服务时需要)
    if ((-not $SkipService) -and (-not $Only -or $Only -eq "service")) {
        $nssmExe = $null
        try { $nssmExe = (Get-Command nssm -ErrorAction Stop).Source } catch {}
        if (-not $nssmExe) {
            Write-Fail "NSSM 未安装。请下载 nssm.cc 并加入 PATH"
            Write-Host "  下载地址: https://nssm.cc/download" -ForegroundColor Yellow
            Write-Host "  或用 -SkipService 跳过服务注册" -ForegroundColor Yellow
            exit 1
        }
        Write-Ok "NSSM: $nssmExe"
    }
}

# ============================================
# Step 2: 安装依赖
# ============================================
if (-not $Only -or $Only -eq "install") {
    Write-Step "Step 2/5: 安装依赖 (uv sync)"

    Push-Location $ProjectDir
    try {
        $prevEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        # 生产环境需要 --extra tdx/qmt 安装 numpy, pandas 等 SDK 依赖
        $syncArgs = @("sync")
        if ($appEnv -eq "production") {
            $syncArgs += @("--extra", "tdx", "--extra", "qmt")
        }
        & uv @syncArgs 2>$null | Out-Null
        $syncExit = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP
        if ($syncExit -ne 0) { throw "uv sync failed (exit code $syncExit)" }
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
    Write-Step "Step 3/5: 测试 TDX 实例启动"

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
        for ($i = 1; $i -le 5; $i++) {
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9001/health" -TimeoutSec 5 -UseBasicParsing
                $body = $resp.Content | ConvertFrom-Json
                Write-Ok "TDX health: status=$($body.status), adapter=$($body.adapter)"
                $tdxOk = $true
                break
            } catch {
                if ($i -lt 5) {
                    Write-Host "  等待 TDX 启动... ($i/5)" -ForegroundColor Yellow
                    Start-Sleep -Seconds 3
                } else {
                    Write-Fail "TDX health 接口无响应 (已重试 5 次)"
                    Get-Content $tdxTestErr -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
                    Get-Content $tdxTestLog -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
                }
            }
        }
        $proc.Kill()
        $proc.WaitForExit(5000)
    }

    if (-not $tdxOk) {
        Write-Host "`n  TDX 测试失败! 请检查上面的错误信息。" -ForegroundColor Red
        Write-Host "  常见问题:" -ForegroundColor Yellow
        Write-Host "    1. APP_ENV=development -> 检查 mock adapter 是否正常" -ForegroundColor Yellow
        Write-Host "    2. APP_ENV=production -> 检查 TDX_SDK_PATH 是否正确, 通达信终端是否已登录" -ForegroundColor Yellow
        Write-Host "    3. 端口 9001 被占用 -> 关闭占用进程" -ForegroundColor Yellow
        if (-not $Only) {
            Write-Host "`n  是否继续注册服务? (Y/N)" -ForegroundColor Yellow
            $cont = Read-Host
            if ($cont -ne "Y") { exit 1 }
        }
    }

    # 测试 QMT 实例 (仅在配置了 QMT_SDK_PATH 时)
    Write-Step "Step 4/5: 测试 QMT 实例启动"

    $qmtSdk = if ($envContent -match 'QMT_SDK_PATH\s*=\s*(.+)') { $Matches[1].Trim() } else { "" }
    if (-not $qmtSdk -or $qmtSdk -eq "") {
        Write-Host "  跳过 QMT 测试 (QMT_SDK_PATH 未配置)" -ForegroundColor Yellow
    } else {
        $qmtTestLog = Join-Path $LogsDir "deploy-test-qmt.log"
        $qmtTestErr = Join-Path $LogsDir "deploy-test-qmt-err.log"
        Write-Host "  启动 QMT 实例 (临时, 仅测试)..."
        $qmtProc = Start-Process -FilePath $venvPython `
            -ArgumentList "-m", "uvicorn", "qmt.main:app", "--host", "127.0.0.1", "--port", "9002" `
            -WorkingDirectory $ProjectDir `
            -RedirectStandardOutput $qmtTestLog `
            -RedirectStandardError $qmtTestErr `
            -PassThru -NoNewWindow

        Start-Sleep -Seconds 3

        if ($qmtProc.HasExited) {
            Write-Fail "QMT 实例启动后立即退出 (exit code: $($qmtProc.ExitCode))"
            Get-Content $qmtTestErr -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
        } else {
            try {
                $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9002/health" -TimeoutSec 5 -UseBasicParsing
                $body = $resp.Content | ConvertFrom-Json
                Write-Ok "QMT health: status=$($body.status), adapter=$($body.adapter)"
            } catch {
                Write-Fail "QMT health 接口无响应: $_"
                Get-Content $qmtTestErr -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "  $_" }
            }
            $qmtProc.Kill()
            $qmtProc.WaitForExit(5000)
        }
    }
}

# ============================================
# Step 5: 注册 NSSM 服务
# ============================================
if ((-not $SkipService) -and (-not $Only -or $Only -eq "service")) {
    Write-Step "Step 5/5: 注册 NSSM 服务"

    $venvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"

    # --- TDX 服务 ---
    $tdxService = "MistTDX"
    $existing = nssm status $tdxService 2>&1
    if ($existing -match "SERVICE_RUNNING|SERVICE_STOPPED") {
        Write-Host "  $tdxService 已存在 (状态: $existing), 跳过注册" -ForegroundColor Yellow
    } else {
        nssm install $tdxService $venvPython "-m uvicorn tdx.main:app --host 0.0.0.0 --port 9001"
        nssm set $tdxService AppDirectory $ProjectDir
        nssm set $tdxService DisplayName "Mist TDX DataSource"
        nssm set $tdxService Description "通达信数据源 HTTP/WS 服务 (port 9001)"
        nssm set $tdxService Start SERVICE_AUTO_START
        nssm set $tdxService AppStdout (Join-Path $LogsDir "tdx-stdout.log")
        nssm set $tdxService AppStderr (Join-Path $LogsDir "tdx-stderr.log")
        nssm set $tdxService AppRotateFiles 1
        nssm set $tdxService AppRotateBytes 10485760
        Write-Ok "$tdxService 服务已注册"
    }

    # --- QMT 服务 ---
    $qmtService = "MistQMT"
    $existing = nssm status $qmtService 2>&1
    if ($existing -match "SERVICE_RUNNING|SERVICE_STOPPED") {
        Write-Host "  $qmtService 已存在 (状态: $existing), 跳过注册" -ForegroundColor Yellow
    } else {
        nssm install $qmtService $venvPython "-m uvicorn qmt.main:app --host 0.0.0.0 --port 9002"
        nssm set $qmtService AppDirectory $ProjectDir
        nssm set $qmtService DisplayName "Mist QMT DataSource"
        nssm set $qmtService Description "QMT 数据源 HTTP/WS 服务 (port 9002)"
        nssm set $qmtService Start SERVICE_AUTO_START
        nssm set $qmtService AppStdout (Join-Path $LogsDir "qmt-stdout.log")
        nssm set $qmtService AppStderr (Join-Path $LogsDir "qmt-stderr.log")
        nssm set $qmtService AppRotateFiles 1
        nssm set $qmtService AppRotateBytes 10485760
        Write-Ok "$qmtService 服务已注册"
    }

    # 启动服务
    Write-Host "`n  启动服务..." -ForegroundColor Cyan
    nssm start $tdxService
    nssm start $qmtService

    Start-Sleep -Seconds 3

    # 最终验证
    Write-Host "`n  最终验证:" -ForegroundColor Cyan
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9001/health" -TimeoutSec 5 -UseBasicParsing
        $body = $resp.Content | ConvertFrom-Json
        Write-Ok "TDX: status=$($body.status), adapter=$($body.adapter)"
    } catch {
        Write-Fail "TDX 服务启动失败"
    }
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:9002/health" -TimeoutSec 5 -UseBasicParsing
        $body = $resp.Content | ConvertFrom-Json
        Write-Ok "QMT: status=$($body.status), adapter=$($body.adapter)"
    } catch {
        Write-Fail "QMT 服务启动失败"
    }
}

Write-Host "`n===== 部署完成 =====" -ForegroundColor Green
Write-Host "  日志目录: $LogsDir"
Write-Host "  管理命令:"
Write-Host "    nssm status MistTDX / MistQMT          # 查看状态"
Write-Host "    nssm restart MistTDX / MistQMT          # 重启服务"
Write-Host "    nssm stop MistTDX / MistQMT             # 停止服务"
Write-Host "    nssm remove MistTDX / MistQMT           # 删除服务"
