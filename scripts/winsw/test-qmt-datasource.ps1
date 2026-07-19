param(
    [string]$BaseUrl = "http://127.0.0.1:9002"
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

try {
    $BaseUrl = $BaseUrl.TrimEnd("/")

    Write-Host "Checking QMT health: $BaseUrl/health"
    $health = Invoke-RestMethod -Method Get -Uri "$BaseUrl/health" -TimeoutSec 20
    foreach ($key in @("status", "instance", "bridge")) {
        Assert-PropertyExists -Object $health -Name $key
    }
    if ($health.instance -ne "qmt") {
        throw "Expected QMT health instance to be qmt, got: $($health.instance)"
    }

    Write-Host "Checking QMT HTTP polling bridge health: $BaseUrl/qmt/bridge/health"
    $bridge = Invoke-RestMethod -Method Get -Uri "$BaseUrl/qmt/bridge/health" -TimeoutSec 20
    foreach ($key in @("ownerId", "pendingCount", "inFlightCount", "resultCount")) {
        Assert-PropertyExists -Object $bridge -Name $key
    }

    Write-Host "QMT datasource smoke test passed."
    exit 0
}
catch {
    Write-Error "QMT datasource smoke test failed: $_"
    exit 1
}
