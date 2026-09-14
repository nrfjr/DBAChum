param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$HostName = 'localhost',

    [ValidateRange(10, 600)]
    [int]$StartupTimeoutSeconds = 90,

    [switch]$SkipCollector
)

$ErrorActionPreference = 'Stop'
$BaseUrl = "http://${HostName}:$Port"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$CollectorStatusScript = Join-Path $BackendDir 'scripts\collector_status.py'

$startupDeadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
$startupReady = $false
$lastStartupError = ''

do {
    try {
        $root = Invoke-WebRequest `
            -Uri "$BaseUrl/" `
            -UseBasicParsing `
            -TimeoutSec 5 `
            -ErrorAction Stop

        if ($root.StatusCode -ne 200 -or $root.Content -notmatch '<div id="app"') {
            throw 'Frontend response was not ready.'
        }

        $ready = Invoke-RestMethod `
            -Uri "$BaseUrl/api/v1/health/ready" `
            -TimeoutSec 5 `
            -ErrorAction Stop

        if (-not $ready.ready -or $ready.mongodb -ne 'healthy') {
            throw "API readiness returned ready=$($ready.ready), mongodb=$($ready.mongodb)."
        }

        $startupReady = $true
        break
    }
    catch {
        $lastStartupError = $_.Exception.Message
        if ((Get-Date) -lt $startupDeadline) {
            Start-Sleep -Seconds 2
        }
    }
} while ((Get-Date) -lt $startupDeadline)

if (-not $startupReady) {
    throw "DBAChum did not become ready within $StartupTimeoutSeconds seconds. Last error: $lastStartupError"
}

Write-Host 'PASS  Production frontend' -ForegroundColor Green
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

    for ($attempt = 1; $attempt -le 15; $attempt++) {
        Push-Location $BackendDir
        try {
            $collectorOutput = @(& $PythonExe -m scripts.collector_status 2>&1)
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
