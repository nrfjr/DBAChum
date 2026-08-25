param(
    [string]$ClientLibDir = 'C:\Oracle\instantclient-basic-windows.x64-12.1.0.2.0\instantclient_12_1'
)

$ErrorActionPreference = 'Stop'

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$BackendDir = Join-Path $ProjectRoot 'backend'
$EnvFile = Join-Path $BackendDir '.env'
$PythonExe = Join-Path $BackendDir '.venv\Scripts\python.exe'
$OciDll = Join-Path $ClientLibDir 'oci.dll'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

if (-not (Test-Path $EnvFile)) {
    throw "backend\.env was not found: $EnvFile"
}
if (-not (Test-Path $PythonExe)) {
    throw "Backend virtual environment was not found: $PythonExe"
}
if (-not (Test-Path $OciDll)) {
    throw "Oracle OCI library was not found: $OciDll"
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

$driverVersion = (& $PythonExe -c "import oracledb; print(oracledb.__version__)").Trim()
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to import python-oracledb from the DBAChum virtual environment.'
}
if ($driverVersion -ne '2.5.1') {
    throw "DBAChum Oracle 10g mode requires python-oracledb 2.5.1. Found $driverVersion. Run: backend\.venv\Scripts\python.exe -m pip install --force-reinstall oracledb==2.5.1"
}

$env:DBACHUM_ORACLE_CLIENT_LIB_DIR = $ClientLibDir
try {
    $clientVersion = (& $PythonExe -c "import os,oracledb; oracledb.init_oracle_client(lib_dir=os.environ['DBACHUM_ORACLE_CLIENT_LIB_DIR']); print('.'.join(str(x) for x in oracledb.clientversion()))").Trim()
    if ($LASTEXITCODE -ne 0) {
        throw 'Oracle Thick-mode validation failed.'
    }
}
finally {
    Remove-Item Env:DBACHUM_ORACLE_CLIENT_LIB_DIR -ErrorAction SilentlyContinue
}

$text = Get-Content $EnvFile -Raw
$text = Set-EnvValue -Text $text -Name 'ORACLE_DRIVER_MODE' -Value 'thick'
$text = Set-EnvValue -Text $text -Name 'ORACLE_CLIENT_LIB_DIR' -Value $ClientLibDir
[System.IO.File]::WriteAllText($EnvFile, $text, $Utf8NoBom)

Write-Host "PASS  Oracle legacy connectivity enabled." -ForegroundColor Green
Write-Host "      python-oracledb: $driverVersion"
Write-Host "      Oracle client:   $clientVersion"
Write-Host "      Client path:     $ClientLibDir"
Write-Host ''
Write-Host 'Restart DBAChum for the new Oracle driver mode to take effect.'
