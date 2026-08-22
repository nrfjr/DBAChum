param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

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
$LogFile = Join-Path $LogDir 'dbachum-server.log'

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
        Move-Item $LogFile (Join-Path $LogDir "dbachum-server-$stamp.log")
    }
}

Get-ChildItem $LogDir -Filter 'dbachum-server-*.log' -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLogs |
    Remove-Item -Force

Set-Location $BackendDir

"[$(Get-Date -Format o)] Starting DBAChum on port $Port" | Out-File -FilePath $LogFile -Append -Encoding utf8

$UvicornArgs = @(
    '-m'
    'uvicorn'
    'app.main:app'
    '--host'
    '0.0.0.0'
    '--port'
    $Port.ToString()
    '--workers'
    '1'
    '--no-access-log'
    '--no-server-header'
)

# Windows PowerShell 5.1 can surface a native program's normal stderr
# logging as NativeCommandError when ErrorActionPreference is Stop.
# Uvicorn legitimately writes log records to stderr, so temporarily allow
# native stderr while still failing on a non-zero process exit code.
$PreviousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'

try {
    & $PythonExe @UvicornArgs *>> $LogFile
    $ExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}

if ($ExitCode -ne 0) {
    throw "DBAChum exited with code $ExitCode."
}

exit 0
