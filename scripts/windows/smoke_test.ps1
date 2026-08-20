param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$HostName = 'localhost'
)

$ErrorActionPreference = 'Stop'
$BaseUrl = "http://${HostName}:$Port"

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

Write-Host ''
Write-Host "PASS  DBAChum is healthy at $BaseUrl" -ForegroundColor Green
