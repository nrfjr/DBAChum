param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [switch]$SkipE2E,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$PreflightScript = Join-Path $PSScriptRoot 'preflight.ps1'
$SmokeScript = Join-Path $PSScriptRoot 'smoke_test.ps1'

function Invoke-NativeStep {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,

        [Parameter(Mandatory = $true)]
        [string]$Executable,

        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,

        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    Write-Host "" 
    Write-Host "==> $Name" -ForegroundColor Cyan

    Push-Location $WorkingDirectory
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'

    try {
        & $Executable @Arguments
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
        Pop-Location
    }

    if ($exitCode -ne 0) {
        throw "$Name failed with exit code $exitCode."
    }

    Write-Host "PASS  $Name" -ForegroundColor Green
}

if (-not (Test-Path $PythonExe)) {
    throw "Backend virtual environment was not found: $PythonExe"
}

$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($null -eq $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}
if ($null -eq $npmCommand) {
    throw 'npm was not found in PATH.'
}

Invoke-NativeStep `
    -Name 'Backend pytest' `
    -Executable $PythonExe `
    -Arguments @('-m', 'pytest', '-q') `
    -WorkingDirectory $BackendDir

Invoke-NativeStep `
    -Name 'Frontend type-check' `
    -Executable $npmCommand.Source `
    -Arguments @('run', 'type-check') `
    -WorkingDirectory $FrontendDir

Invoke-NativeStep `
    -Name 'Frontend lint' `
    -Executable $npmCommand.Source `
    -Arguments @('run', 'lint') `
    -WorkingDirectory $FrontendDir

Invoke-NativeStep `
    -Name 'Frontend production build' `
    -Executable $npmCommand.Source `
    -Arguments @('run', 'build') `
    -WorkingDirectory $FrontendDir

if (-not $SkipE2E) {
    Invoke-NativeStep `
        -Name 'Frontend Playwright E2E' `
        -Executable $npmCommand.Source `
        -Arguments @('run', 'e2e') `
        -WorkingDirectory $FrontendDir
}
else {
    Write-Host 'WARN  Playwright E2E skipped.' -ForegroundColor Yellow
}

Write-Host ""
Write-Host '==> Native Windows preflight' -ForegroundColor Cyan
& $PreflightScript -Port $Port -RequireMongoTools -StrictProduction

if (-not $SkipSmoke) {
    Write-Host ""
    Write-Host '==> Live deployment smoke test' -ForegroundColor Cyan
    & $SmokeScript -Port $Port
}
else {
    Write-Host 'WARN  Live smoke test skipped.' -ForegroundColor Yellow
}

Write-Host ""
Write-Host 'PASS  DBAChum release-readiness checks completed.' -ForegroundColor Green
