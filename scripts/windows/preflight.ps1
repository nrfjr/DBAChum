param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [switch]$RequireMongoTools,

    [switch]$StrictProduction
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

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Text,

        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $match = [regex]::Match(
        $Text,
        "(?m)^$([regex]::Escape($Name))=(.*?)\s*$"
    )

    if (-not $match.Success) {
        return $null
    }

    return $match.Groups[1].Value.Trim().Trim('"').Trim("'")
}

function Resolve-MongoTool {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $command = Get-Command "$Name.exe" -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $toolsRoot = Join-Path $env:ProgramFiles 'MongoDB\Tools'
    if (Test-Path $toolsRoot) {
        $candidate = Get-ChildItem `
            -Path $toolsRoot `
            -Recurse `
            -Filter "$Name.exe" `
            -File `
            -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1

        if ($null -ne $candidate) {
            return $candidate.FullName
        }
    }

    return $null
}

if (Test-Path $PythonExe) { Pass 'Backend virtual environment exists' } else { Fail "Missing $PythonExe" }
if (Test-Path $EnvFile) { Pass 'backend/.env exists' } else { Fail 'backend/.env is missing' }
if (Test-Path $IndexFile) { Pass 'Production frontend build exists' } else { Fail 'frontend/dist/index.html is missing' }

$envText = ''
if (Test-Path $EnvFile) {
    $envText = Get-Content $EnvFile -Raw

    $environment = Get-EnvValue -Text $envText -Name 'ENVIRONMENT'
    if ($environment -eq 'production') {
        Pass 'ENVIRONMENT=production'
    }
    elseif ($StrictProduction) {
        Fail 'ENVIRONMENT must be production for the release gate'
    }
    else {
        Warn 'ENVIRONMENT is not set to production'
    }

    $apiDocsEnabled = Get-EnvValue -Text $envText -Name 'API_DOCS_ENABLED'
    if ($apiDocsEnabled -eq 'false') {
        Pass 'Production API documentation is disabled'
    }
    elseif ($StrictProduction) {
        Fail 'API_DOCS_ENABLED=false is required for the release gate'
    }
    else {
        Warn 'API documentation is enabled or not explicitly disabled'
    }

    $key = Get-EnvValue -Text $envText -Name 'CONNECTION_ENCRYPTION_KEY'
    if ($key -match '^[A-Za-z0-9_-]{43}=$') {
        Pass 'Connection encryption key format looks valid'
    }
    else {
        Fail 'CONNECTION_ENCRYPTION_KEY does not look like a Fernet key'
    }

    $cookieSecure = Get-EnvValue -Text $envText -Name 'COOKIE_SECURE'
    if ($cookieSecure -eq 'true') {
        Pass 'Secure cookies enabled'
    }
    else {
        Warn 'COOKIE_SECURE=false; use only on an approved HTTP-only internal network and enable it behind HTTPS'
    }

    $trustedHosts = Get-EnvValue -Text $envText -Name 'TRUSTED_HOSTS'
    if ([string]::IsNullOrWhiteSpace($trustedHosts)) {
        Fail 'TRUSTED_HOSTS must contain the hostnames/IP addresses clients use'
    }
    elseif ($trustedHosts.Split(',').Trim() -contains '*') {
        if ($StrictProduction) {
            Fail "TRUSTED_HOSTS cannot contain '*' in production"
        }
        else {
            Warn "TRUSTED_HOSTS contains '*'"
        }
    }
    else {
        Pass 'Trusted Host header allow-list is configured'
    }

    $corsOrigins = Get-EnvValue -Text $envText -Name 'CORS_ORIGINS'
    if ($corsOrigins -match '(^|,)\s*\*\s*(,|$)') {
        Fail "CORS_ORIGINS cannot contain '*'"
    }
    elseif ([string]::IsNullOrWhiteSpace($corsOrigins)) {
        Pass 'CORS disabled for same-origin production frontend'
    }
    else {
        Warn "CORS is enabled for explicit origin(s): $corsOrigins"
    }
}

$gitCommand = Get-Command git.exe -ErrorAction SilentlyContinue
if ($null -eq $gitCommand) {
    $gitCommand = Get-Command git -ErrorAction SilentlyContinue
}
if ($null -ne $gitCommand -and (Test-Path (Join-Path $ProjectRoot '.git'))) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location $ProjectRoot
    try {
        & $gitCommand.Source ls-files --error-unmatch backend/.env *> $null
        $envTracked = $LASTEXITCODE -eq 0
    }
    finally {
        Pop-Location
        $ErrorActionPreference = $previousPreference
    }

    if ($envTracked) {
        Fail 'backend/.env is tracked by Git; remove it from source control immediately'
    }
    else {
        Pass 'backend/.env is not tracked by Git'
    }
}

# Oracle runtime compatibility. Thick mode is required for Oracle 10g.
$oracleDriverMode = Get-EnvValue -Text $envText -Name 'ORACLE_DRIVER_MODE'
if ([string]::IsNullOrWhiteSpace($oracleDriverMode)) {
    $oracleDriverMode = 'thin'
}
else {
    $oracleDriverMode = $oracleDriverMode.Trim().ToLowerInvariant()
}

if ($oracleDriverMode -eq 'thick') {
    $oracleClientLibDir = Get-EnvValue -Text $envText -Name 'ORACLE_CLIENT_LIB_DIR'
    if ([string]::IsNullOrWhiteSpace($oracleClientLibDir)) {
        Fail 'ORACLE_CLIENT_LIB_DIR is required when ORACLE_DRIVER_MODE=thick'
    }
    else {
        $ociDll = Join-Path $oracleClientLibDir 'oci.dll'
        if (Test-Path $ociDll) {
            Pass "Oracle OCI library found: $ociDll"
        }
        else {
            Fail "Oracle OCI library not found: $ociDll"
        }

        if (Test-Path $PythonExe) {
            $previousPreference = $ErrorActionPreference
            $ErrorActionPreference = 'Continue'
            $env:DBACHUM_ORACLE_CLIENT_LIB_DIR = $oracleClientLibDir
            try {
                $oracleCheck = & $PythonExe -c "import os,oracledb; print('driver=' + oracledb.__version__); oracledb.init_oracle_client(lib_dir=os.environ['DBACHUM_ORACLE_CLIENT_LIB_DIR']); print('client=' + '.'.join(str(x) for x in oracledb.clientversion()))" 2>&1
                $oracleExitCode = $LASTEXITCODE
            }
            finally {
                Remove-Item Env:DBACHUM_ORACLE_CLIENT_LIB_DIR -ErrorAction SilentlyContinue
                $ErrorActionPreference = $previousPreference
            }

            if ($oracleExitCode -eq 0) {
                Pass 'Oracle Thick mode initializes successfully'
                $oracleCheck | ForEach-Object { Write-Host "      $_" -ForegroundColor DarkGray }
            }
            else {
                Fail "Oracle Thick mode validation failed: $($oracleCheck -join ' ')"
            }
        }
    }
}
elseif ($oracleDriverMode -eq 'thin') {
    Warn 'Oracle driver is Thin mode; Oracle 10g connections are unavailable'
}
else {
    Fail "ORACLE_DRIVER_MODE must be thin or thick; found '$oracleDriverMode'"
}

$mongoUri = Get-EnvValue -Text $envText -Name 'MONGODB_URI'
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

$firewallRuleName = "DBAChum TCP $Port"
$firewallRule = Get-NetFirewallRule `
    -DisplayName $firewallRuleName `
    -ErrorAction SilentlyContinue

if ($null -ne $firewallRule) {
    $addressFilter = $firewallRule |
        Get-NetFirewallAddressFilter

    $remoteAddresses = @($addressFilter.RemoteAddress)
    if ($remoteAddresses -contains 'Any') {
        if ($StrictProduction) {
            Fail "Firewall rule '$firewallRuleName' allows Any remote address; reinstall it with LocalSubnet or a management subnet"
        }
        else {
            Warn "Firewall rule '$firewallRuleName' allows Any remote address"
        }
    }
    else {
        Pass "DBAChum firewall rule is source-restricted: $($remoteAddresses -join ', ')"
    }
}
else {
    Pass 'No DBAChum-managed inbound firewall rule is installed'
}

$mongoDump = Resolve-MongoTool -Name 'mongodump'
$mongoRestore = Resolve-MongoTool -Name 'mongorestore'
if ($null -ne $mongoDump -and $null -ne $mongoRestore) {
    Pass 'MongoDB Database Tools found'
    Write-Host "      mongodump: $mongoDump" -ForegroundColor DarkGray
    Write-Host "      mongorestore: $mongoRestore" -ForegroundColor DarkGray
}
elseif ($RequireMongoTools) {
    Fail 'mongodump.exe/mongorestore.exe are required but were not found'
}
else {
    Warn 'MongoDB Database Tools not found; backup/restore helpers will need them'
}

if ($Failed) {
    Write-Host ''
    throw 'DBAChum native Windows preflight failed.'
}

Write-Host ''
Write-Host 'PASS  DBAChum native Windows preflight checks passed.' -ForegroundColor Green
