param(
    [string]$BaseUrl = "http://127.0.0.1:9001",
    [string]$WsUrl = "ws://127.0.0.1:9001/ws/quote/smoke-test",
    [string]$Symbol = "600519.SH",
    [switch]$SkipWebSocket
)

$ErrorActionPreference = "Stop"

function Assert-PropertyExists {
    param(
        [object]$Object,
        [string]$Name
    )

    if ($null -eq $Object -or -not ($Object.PSObject.Properties.Name -contains $Name)) {
        throw "Expected property '$Name' was not present."
    }
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

function Invoke-JsonPost {
    param(
        [string]$Uri,
        [hashtable]$Payload
    )

    $body = $Payload | ConvertTo-Json -Depth 10 -Compress
    return Invoke-RestMethod `
        -Method Post `
        -Uri $Uri `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 20
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

    $json = $Payload | ConvertTo-Json -Depth 10 -Compress
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    $segment = [System.ArraySegment[byte]]::new($bytes)
    [void]$Socket.SendAsync(
        $segment,
        [System.Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        [System.Threading.CancellationToken]::None
    ).GetAwaiter().GetResult()
}

try {
    $BaseUrl = $BaseUrl.TrimEnd("/")
    $rawSymbol = ConvertTo-TdxHttpSymbol -Symbol $Symbol

    Write-Host "Checking health: $BaseUrl/health"
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 20
    foreach ($key in @("tdxHttpReachable", "tqInitialized", "eventQueueDepth", "collectorState")) {
        Assert-PropertyExists -Object $health -Name $key
    }
    Write-Host "Health keys present."

    Write-Host "Checking raw TDX call endpoint."
    $raw = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/raw/tdx/call" `
        -Payload @{
            method = "get_market_data"
            params = @{
                stock_list = @($rawSymbol)
                field_list = @("Open", "High", "Low", "Close", "Volume", "Amount")
                period = "1d"
                count = 1
                dividend_type = "none"
            }
        }
    Assert-EnvelopeOk -Envelope $raw -Name "raw TDX call"

    Write-Host "Checking normalized bars query endpoint."
    $bars = Invoke-JsonPost `
        -Uri "$BaseUrl/v1/bars/query" `
        -Payload @{ symbols = @($Symbol); period = "1m"; count = 1 }
    Assert-EnvelopeOk -Envelope $bars -Name "bars query"

    if (-not $SkipWebSocket) {
        Write-Host "Checking WebSocket bridge: $WsUrl"
        $socket = [System.Net.WebSockets.ClientWebSocket]::new()
        try {
            $connectCts = [System.Threading.CancellationTokenSource]::new()
            $connectCts.CancelAfter([TimeSpan]::FromSeconds(15))
            [void]$socket.ConnectAsync([Uri]$WsUrl, $connectCts.Token).GetAwaiter().GetResult()
            $connectCts.Dispose()

            $ready = Receive-WebSocketText -Socket $socket | ConvertFrom-Json
            if ($ready.type -ne "ready") {
                throw "Expected WebSocket ready message, got: $($ready | ConvertTo-Json -Compress -Depth 8)"
            }

            Send-WebSocketJson -Socket $socket -Payload @{
                "type" = "ping"
            }

            $pong = Receive-WebSocketText -Socket $socket | ConvertFrom-Json
            if ($pong.type -ne "pong") {
                throw "Expected WebSocket pong message, got: $($pong | ConvertTo-Json -Compress -Depth 8)"
            }
        }
        finally {
            if ($socket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
                [void]$socket.CloseAsync(
                    [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                    "smoke complete",
                    [System.Threading.CancellationToken]::None
                ).GetAwaiter().GetResult()
            }
            $socket.Dispose()
        }
    }
    else {
        Write-Host "Skipping WebSocket bridge check."
    }

    Write-Host "TDX datasource smoke test passed."
    exit 0
}
catch {
    Write-Error "TDX datasource smoke test failed: $_"
    exit 1
}
