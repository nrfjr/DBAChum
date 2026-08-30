param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$HostName = 'localhost',

    [switch]$SkipCollector
)

$ErrorActionPreference = 'Stop'
$BaseUrl = "http://${HostName}:$Port"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$CollectorStatusScript = Join-Path $BackendDir 'scripts\collector_status.py'

$root = Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing -TimeoutSec 10
if ($root.StatusCode -ne 200 -or $root.Content -notmatch '<div id="app"') {
    throw 'Frontend smoke check failed.'
}
Write-Host 'PASS  Production frontend' -ForegroundColor Green

$ready = Invoke-RestMethod -Uri "$BaseUrl/api/v1/health/ready" -TimeoutSec 10
if (-not $ready.ready -or $ready.mongodb -ne 'healthy') {
    throw "API readiness failed: $($ready | ConvertTo-Json -Compress)"
}
Write-Host 'PASS  API readiness + MongoDB' -ForegroundColor Green

if (-not $SkipCollector) {
    if (-not (Test-Path $PythonExe)) {
        throw "Backend virtual environment was not found: $PythonExe"
    }
    if (-not (Test-Path $CollectorStatusScript)) {
        throw "Collector status script was not found: $CollectorStatusScript"
    }

    $collectorHealthy = $false
    $collectorOutput = @()

    # The collector writes a 10-second heartbeat. Give a newly started stack a
    # short grace period before declaring the lifecycle unhealthy.
    for ($attempt = 1; $attempt -le 15; $attempt++) {
        Push-Location $BackendDir
        try {
            $collectorOutput = @(& $PythonExe scripts\collector_status.py 2>&1)
        }
        finally {
            Pop-Location
        }

        if (($collectorOutput -join "`n") -match '(?m)^Alive:\s+yes\s*$') {
            $collectorHealthy = $true
            break
        }

        if ($attempt -lt 15) {
            Start-Sleep -Seconds 2
        }
    }

    if (-not $collectorHealthy) {
        throw "Collector smoke check failed:`n$($collectorOutput -join "`n")"
    }

    Write-Host 'PASS  Background telemetry collector' -ForegroundColor Green
}

Write-Host ''
Write-Host "PASS  DBAChum is healthy at $BaseUrl" -ForegroundColor Green
