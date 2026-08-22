param(
    [string]$PythonCommand = 'python',
    [switch]$SkipDependencies
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendIndex = Join-Path $ProjectRoot 'frontend\dist\index.html'
$Requirements = Join-Path $BackendDir 'requirements.txt'
$VenvPython = Join-Path $BackendDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $BackendDir '.env'
$EnvTemplate = Join-Path $ProjectRoot 'deployment\windows\backend.env.example'
$VersionFile = Join-Path $ProjectRoot 'VERSION'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Assert-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Get-DefaultTrustedHosts {
    $hosts = @('localhost', '127.0.0.1')

    if (-not [string]::IsNullOrWhiteSpace($env:COMPUTERNAME)) {
        $hosts += $env:COMPUTERNAME
    }

    try {
        $hosts += Get-NetIPAddress `
            -AddressFamily IPv4 `
            -ErrorAction Stop |
            Where-Object {
                $_.IPAddress -ne '127.0.0.1' -and
                $_.IPAddress -notlike '169.254.*'
            } |
            Select-Object -ExpandProperty IPAddress
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

function Set-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Name,

        [AllowEmptyString()]
        [string]$Value
    )

    $pattern = "(?m)^$([regex]::Escape($Name))=.*$"
    $line = "$Name=$Value"

    if ($Text -match $pattern) {
        return [regex]::Replace($Text, $pattern, $line)
    }

    if (-not $Text.EndsWith("`n")) {
        $Text += "`r`n"
    }

    return $Text + $line + "`r`n"
}

if (-not (Test-Path $FrontendIndex)) {
    throw "Compiled frontend is missing: $FrontendIndex"
}
if (-not (Test-Path $Requirements)) {
    throw "Backend requirements are missing: $Requirements"
}
if (-not (Test-Path $EnvTemplate)) {
    throw "Production environment template is missing: $EnvTemplate"
}
if (-not (Test-Path $VersionFile)) {
    throw "VERSION file is missing: $VersionFile"
}

Assert-Command $PythonCommand
$Version = (Get-Content $VersionFile -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($Version)) {
    throw 'VERSION is empty.'
}

if (-not (Test-Path $EnvFile)) {
    $text = Get-Content $EnvTemplate -Raw
    $text = $text.Replace(
        'CONNECTION_ENCRYPTION_KEY=replace-me',
        "CONNECTION_ENCRYPTION_KEY=$(New-FernetKey)"
    )
    $text = $text.Replace(
        'TRUSTED_HOSTS=__TRUSTED_HOSTS__',
        "TRUSTED_HOSTS=$(Get-DefaultTrustedHosts)"
    )
    $text = Set-EnvValue -Text $text -Name 'APP_VERSION' -Value $Version

    [System.IO.File]::WriteAllText($EnvFile, $text, $Utf8NoBom)
    Write-Host "Created backend\.env for DBAChum $Version with a generated encryption key."
}
else {
    $text = Get-Content $EnvFile -Raw
    $updated = Set-EnvValue -Text $text -Name 'APP_VERSION' -Value $Version
    [System.IO.File]::WriteAllText($EnvFile, $updated, $Utf8NoBom)
    Write-Host "Preserved existing backend\.env and updated APP_VERSION=$Version."
}

if (-not $SkipDependencies) {
    if (-not (Test-Path $VenvPython)) {
        Write-Host 'Creating backend virtual environment...'
        & $PythonCommand -m venv (Join-Path $BackendDir '.venv')
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to create backend virtual environment.'
        }
    }

    Write-Host 'Installing backend runtime dependencies...'
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to upgrade pip.'
    }

    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install backend requirements.'
    }
}
elseif (-not (Test-Path $VenvPython)) {
    throw '-SkipDependencies was used but backend\.venv does not exist.'
}

$mongoService = Get-Service -Name 'MongoDB' -ErrorAction SilentlyContinue
if ($null -eq $mongoService) {
    Write-Warning "MongoDB Windows service named 'MongoDB' was not found. If MongoDB is remote, verify MONGODB_URI in backend\.env."
}
elseif ($mongoService.Status -eq 'Running') {
    Write-Host 'MongoDB Windows service is running.'
}
else {
    Write-Warning "MongoDB Windows service is $($mongoService.Status)."
}

Write-Host ''
Write-Host "PASS  DBAChum $Version runtime is installed." -ForegroundColor Green
Write-Host 'Next:'
Write-Host '  1. Review backend\.env.'
Write-Host '  2. Run scripts\windows\preflight.ps1 -RequireMongoTools -StrictProduction.'
Write-Host '  3. From elevated PowerShell, run scripts\windows\install_startup_task.ps1.'
