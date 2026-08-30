param(
    [ValidateRange(1, 60)]
    [int]$KeepLogs = 5,

    [ValidateRange(1, 1024)]
    [int]$MaxLogSizeMB = 10
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $BackendDir '.env'
$LogDir = Join-Path $ProjectRoot 'logs'
$LogFile = Join-Path $LogDir 'dbachum-collector.log'

if (-not (Test-Path $PythonExe)) {
    throw "Backend virtual environment was not found: $PythonExe. Run scripts\windows\setup.ps1 first."
}

if (-not (Test-Path $EnvFile)) {
    throw "Backend .env was not found: $EnvFile. Run scripts\windows\setup.ps1 first."
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if (Test-Path $LogFile) {
    $maxBytes = $MaxLogSizeMB * 1MB
    if ((Get-Item $LogFile).Length -ge $maxBytes) {
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        Move-Item $LogFile (Join-Path $LogDir "dbachum-collector-$stamp.log")
    }
}

Get-ChildItem $LogDir -Filter 'dbachum-collector-*.log' -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLogs |
    Remove-Item -Force

Set-Location $BackendDir
"[$(Get-Date -Format o)] Starting DBAChum background collector" | Out-File -FilePath $LogFile -Append -Encoding utf8

$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

try {
    & $PythonExe -m app.collector *>> $LogFile
    $ExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}

if ($ExitCode -ne 0) {
    throw "DBAChum collector exited with code $ExitCode."
}

exit 0
