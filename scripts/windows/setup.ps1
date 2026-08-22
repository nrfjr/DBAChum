param(
    [string]$PythonCommand = 'python',
    [string]$NpmCommand = 'npm',
    [switch]$SkipDependencies
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $BackendDir '.env'
$EnvTemplate = Join-Path $ProjectRoot 'deployment\windows\backend.env.example'

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}


function Get-DefaultTrustedHosts {
    $hosts = @(
        'localhost'
        '127.0.0.1'
    )

    if (-not [string]::IsNullOrWhiteSpace($env:COMPUTERNAME)) {
        $hosts += $env:COMPUTERNAME
    }

    try {
        $addresses = Get-NetIPAddress `
            -AddressFamily IPv4 `
            -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -ne '127.0.0.1' -and
                $_.IPAddress -notlike '169.254.*'
            } |
            Select-Object -ExpandProperty IPAddress

        $hosts += $addresses
    }
    catch {
        Write-Warning 'Unable to enumerate local IPv4 addresses for TRUSTED_HOSTS.'
    }

    return (($hosts | Where-Object { $_ } | Sort-Object -Unique) -join ',')
}

function New-FernetKey {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
    }
    finally {
        $rng.Dispose()
    }

    return [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
}

Assert-Command $PythonCommand
Assert-Command $NpmCommand

if (-not (Test-Path $EnvFile)) {
    $template = Get-Content $EnvTemplate -Raw
    $template = $template.Replace('CONNECTION_ENCRYPTION_KEY=replace-me', "CONNECTION_ENCRYPTION_KEY=$(New-FernetKey)")
    $template = $template.Replace('TRUSTED_HOSTS=__TRUSTED_HOSTS__', "TRUSTED_HOSTS=$(Get-DefaultTrustedHosts)")
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($EnvFile, $template, $utf8NoBom)
    Write-Host "Created $EnvFile with a generated encryption key."
}
else {
    Write-Host "Keeping existing $EnvFile"
}

if (-not $SkipDependencies) {
    if (-not (Test-Path $VenvPython)) {
        Write-Host 'Creating backend virtual environment...'
        & $PythonCommand -m venv (Join-Path $BackendDir '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'Failed to create backend virtual environment.' }
    }

    Write-Host 'Installing backend dependencies...'
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw 'Failed to upgrade pip.' }
    & $VenvPython -m pip install -r (Join-Path $BackendDir 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to install backend dependencies.' }

    Write-Host 'Installing frontend dependencies...'
    Push-Location $FrontendDir
    try {
        & $NpmCommand ci
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
    }
    finally {
        Pop-Location
    }
}

Write-Host 'Building production frontend...'
$previousApiBaseUrl = $env:VITE_API_BASE_URL
$env:VITE_API_BASE_URL = '/api/v1'
Push-Location $FrontendDir
try {
    & $NpmCommand run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend production build failed.' }
}
finally {
    Pop-Location
    $env:VITE_API_BASE_URL = $previousApiBaseUrl
}

$IndexFile = Join-Path $FrontendDir 'dist\index.html'
if (-not (Test-Path $IndexFile)) {
    throw "Frontend build completed without $IndexFile"
}

$mongoService = Get-Service -Name 'MongoDB' -ErrorAction SilentlyContinue
if ($null -eq $mongoService) {
    Write-Warning "MongoDB Windows service named 'MongoDB' was not found. DBAChum can still use a remote MongoDB; verify MONGODB_URI in backend\.env."
}
elseif ($mongoService.Status -ne 'Running') {
    Write-Warning "MongoDB service exists but is $($mongoService.Status). Start it before DBAChum."
}
else {
    Write-Host 'MongoDB Windows service is running.'
}

Write-Host ''
Write-Host 'PASS  DBAChum native Windows build is ready.'
Write-Host 'Next: run scripts\windows\preflight.ps1, then install_startup_task.ps1.'
