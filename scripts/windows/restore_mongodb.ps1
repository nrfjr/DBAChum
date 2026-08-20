param(
    [Parameter(Mandatory = $true)]
    [string]$Archive,

    [Parameter(Mandatory = $true)]
    [string]$ConfirmRestore,

    [string]$TaskName = 'DBAChum',
    [string]$MongoUri = '',
    [string]$Database = ''
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$EnvFile = Join-Path $ProjectRoot 'backend\.env'

function Get-EnvValue([string]$Name) {
    if (-not (Test-Path $EnvFile)) { return $null }
    $line = Get-Content $EnvFile | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
    if ($null -eq $line) { return $null }
    return ($line -split '=', 2)[1].Trim()
}

if ($ConfirmRestore -cne 'RESTORE') {
    throw 'Restore refused. Re-run with -ConfirmRestore RESTORE.'
}

if ([string]::IsNullOrWhiteSpace($MongoUri)) {
    $MongoUri = Get-EnvValue 'MONGODB_URI'
    if ([string]::IsNullOrWhiteSpace($MongoUri)) { $MongoUri = 'mongodb://localhost:27017' }
}
if ([string]::IsNullOrWhiteSpace($Database)) {
    $Database = Get-EnvValue 'MONGODB_DATABASE'
    if ([string]::IsNullOrWhiteSpace($Database)) { $Database = 'dbachum' }
}

$resolvedArchive = (Resolve-Path $Archive).Path
$mongorestore = Get-Command mongorestore.exe -ErrorAction SilentlyContinue
if ($null -eq $mongorestore) {
    throw 'mongorestore.exe was not found in PATH. Install MongoDB Database Tools first.'
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$taskWasRunning = $null -ne $task -and $task.State -eq 'Running'

try {
    if ($taskWasRunning) {
        Stop-ScheduledTask -TaskName $TaskName
        Start-Sleep -Seconds 2
    }

    & $mongorestore.Source `
        --uri=$MongoUri `
        --nsInclude="$Database.*" `
        --drop `
        --archive=$resolvedArchive `
        --gzip

    if ($LASTEXITCODE -ne 0) {
        throw "mongorestore failed with exit code $LASTEXITCODE"
    }

    Write-Host 'PASS  MongoDB restore completed.' -ForegroundColor Green
}
finally {
    if ($taskWasRunning) {
        Start-ScheduledTask -TaskName $TaskName
    }
}
