param(
    [string]$TaskName = 'DBAChum',
    [string]$MongoUri = '',
    [string]$Database = '',
    [string]$BackupDirectory = '',
    [switch]$Online
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

if ([string]::IsNullOrWhiteSpace($MongoUri)) {
    $MongoUri = Get-EnvValue 'MONGODB_URI'
    if ([string]::IsNullOrWhiteSpace($MongoUri)) { $MongoUri = 'mongodb://localhost:27017' }
}
if ([string]::IsNullOrWhiteSpace($Database)) {
    $Database = Get-EnvValue 'MONGODB_DATABASE'
    if ([string]::IsNullOrWhiteSpace($Database)) { $Database = 'dbachum' }
}
if ([string]::IsNullOrWhiteSpace($BackupDirectory)) {
    $BackupDirectory = Join-Path $ProjectRoot 'backups'
}

$mongodump = Get-Command mongodump.exe -ErrorAction SilentlyContinue
if ($null -eq $mongodump) {
    throw 'mongodump.exe was not found in PATH. Install MongoDB Database Tools first.'
}

New-Item -ItemType Directory -Force -Path $BackupDirectory | Out-Null
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$archive = Join-Path $BackupDirectory "dbachum-mongodb-$stamp.archive.gz"
$taskWasRunning = $false

try {
    if (-not $Online) {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -ne $task -and $task.State -eq 'Running') {
            $taskWasRunning = $true
            Stop-ScheduledTask -TaskName $TaskName
            Start-Sleep -Seconds 2
        }
    }

    & $mongodump.Source `
        --uri=$MongoUri `
        --db=$Database `
        --archive=$archive `
        --gzip

    if ($LASTEXITCODE -ne 0) {
        throw "mongodump failed with exit code $LASTEXITCODE"
    }

    if (-not (Test-Path $archive)) {
        throw 'mongodump completed without producing the archive.'
    }

    Write-Host "PASS  Backup created: $archive" -ForegroundColor Green
}
finally {
    if ($taskWasRunning) {
        Start-ScheduledTask -TaskName $TaskName
    }
}
