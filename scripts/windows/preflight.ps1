param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [switch]$RequireMongoTools
)

$ErrorActionPreference = 'Stop'
$Failed = $false

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$FrontendDir = Join-Path $ProjectRoot 'frontend'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$EnvFile = Join-Path $BackendDir '.env'
$IndexFile = Join-Path $FrontendDir 'dist\index.html'

function Pass([string]$Message) { Write-Host "PASS  $Message" -ForegroundColor Green }
function Warn([string]$Message) { Write-Host "WARN  $Message" -ForegroundColor Yellow }
function Fail([string]$Message) { Write-Host "FAIL  $Message" -ForegroundColor Red; $script:Failed = $true }

if (Test-Path $PythonExe) { Pass 'Backend virtual environment exists' } else { Fail "Missing $PythonExe" }
if (Test-Path $EnvFile) { Pass 'backend/.env exists' } else { Fail 'backend/.env is missing' }
if (Test-Path $IndexFile) { Pass 'Production frontend build exists' } else { Fail 'frontend/dist/index.html is missing' }

if (Test-Path $EnvFile) {
    $envText = Get-Content $EnvFile -Raw
    if ($envText -match '(?m)^ENVIRONMENT=production\s*$') { Pass 'ENVIRONMENT=production' } else { Warn 'ENVIRONMENT is not set to production' }
    if ($envText -match '(?m)^CONNECTION_ENCRYPTION_KEY=([A-Za-z0-9_-]{43}=)\s*$') { Pass 'Connection encryption key format looks valid' } else { Fail 'CONNECTION_ENCRYPTION_KEY does not look like a Fernet key' }
    if ($envText -match '(?m)^COOKIE_SECURE=true\s*$') { Pass 'Secure cookies enabled' } else { Warn 'COOKIE_SECURE=false; acceptable for HTTP-only internal deployment, but enable it behind HTTPS' }
}

$mongoUri = ''
if (Test-Path $EnvFile) {
    $mongoUriMatch = [regex]::Match($envText, '(?m)^MONGODB_URI=(.+?)\s*$')
    if ($mongoUriMatch.Success) {
        $mongoUri = $mongoUriMatch.Groups[1].Value.Trim()
    }
}

$usesLocalMongo = (
    [string]::IsNullOrWhiteSpace($mongoUri) -or
    $mongoUri -match 'mongodb(?:\+srv)?://(?:[^@/]+@)?(?:localhost|127\.0\.0\.1)(?::|/|$)'
)

if ($usesLocalMongo) {
    $mongoService = Get-Service -Name 'MongoDB' -ErrorAction SilentlyContinue
    if ($null -eq $mongoService) {
        Fail "MONGODB_URI points to localhost but the 'MongoDB' Windows service was not found"
    }
    elseif ($mongoService.Status -eq 'Running') {
        Pass 'MongoDB Windows service is running'
    }
    else {
        Fail "MongoDB service is $($mongoService.Status)"
    }
}
else {
    Pass 'MONGODB_URI points to a remote MongoDB deployment'
}

$listener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($null -eq $listener) {
    Pass "TCP port $Port is available"
}
else {
    Warn "TCP port $Port is already listening; this is expected if DBAChum is currently running"
}

$mongoDump = Get-Command mongodump.exe -ErrorAction SilentlyContinue
$mongoRestore = Get-Command mongorestore.exe -ErrorAction SilentlyContinue
if ($null -ne $mongoDump -and $null -ne $mongoRestore) {
    Pass 'MongoDB Database Tools found in PATH'
}
elseif ($RequireMongoTools) {
    Fail 'mongodump.exe/mongorestore.exe are required but were not found in PATH'
}
else {
    Warn 'MongoDB Database Tools not found in PATH; backup/restore helpers will need them'
}

if ($Failed) {
    Write-Host ''
    throw 'DBAChum native Windows preflight failed.'
}

Write-Host ''
Write-Host 'PASS  DBAChum native Windows preflight checks passed.' -ForegroundColor Green
