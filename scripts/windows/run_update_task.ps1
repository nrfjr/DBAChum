param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$ReleaseVersion,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{12,32}$')]
    [string]$UpdateId,

    [string]$TargetRoot = '',

    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$TaskName = 'DBAChum',

    [switch]$ValidateOnly,
    [switch]$SkipDatabaseBackup,
    [switch]$SkipSmoke,
    [switch]$AllowSameVersion
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Resolve-FullPath([string]$Path, [string]$BaseDirectory = '') {
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw 'A required path was empty.'
    }

    if ([System.IO.Path]::IsPathRooted($Path)) {
        return [System.IO.Path]::GetFullPath($Path)
    }

    if ([string]::IsNullOrWhiteSpace($BaseDirectory)) {
        $BaseDirectory = (Get-Location).Path
    }

    return [System.IO.Path]::GetFullPath((Join-Path $BaseDirectory $Path))
}

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
else {
    $TargetRoot = Resolve-FullPath $TargetRoot
}

$UpdateRoot = Join-Path $TargetRoot '.update'
$LogRoot = Join-Path $UpdateRoot 'logs'
$StatusPath = Join-Path $UpdateRoot 'status.json'
$StdoutPath = Join-Path $LogRoot "update-$UpdateId.out.log"
$StderrPath = Join-Path $LogRoot "update-$UpdateId.err.log"
$CombinedLogPath = Join-Path $LogRoot "update-$UpdateId.log"
$UpdaterScript = Join-Path $TargetRoot 'scripts\windows\update_dbachum.ps1'
$VersionFile = Join-Path $TargetRoot 'VERSION'

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Read-ExistingStatus {
    if (-not (Test-Path $StatusPath -PathType Leaf)) {
        return $null
    }

    try {
        return Get-Content $StatusPath -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Write-UpdateStatus {
    param(
        [Parameter(Mandatory = $true)]
        [string]$State,

        [Parameter(Mandatory = $true)]
        [string]$Message,

        [AllowNull()]
        [string]$FinishedAt = $null,

        [AllowNull()]
        [string]$InstalledVersion = $null
    )

    $existing = Read-ExistingStatus
    $createdAt = if ($null -ne $existing -and $existing.created_at) {
        [string]$existing.created_at
    }
    else {
        [DateTime]::UtcNow.ToString('o')
    }

    $startedAt = if ($State -eq 'queued') {
        $null
    }
    elseif ($null -ne $existing -and $existing.started_at) {
        [string]$existing.started_at
    }
    else {
        [DateTime]::UtcNow.ToString('o')
    }

    $document = [ordered]@{
        update_id = $UpdateId
        state = $State
        requested_version = $ReleaseVersion
        installed_version = $InstalledVersion
        created_at = $createdAt
        started_at = $startedAt
        finished_at = $FinishedAt
        message = $Message
        log_file = ".update/logs/update-$UpdateId.log"
    }

    $temporaryPath = "$StatusPath.$PID.tmp"
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        ($document | ConvertTo-Json -Depth 4),
        $Utf8NoBom
    )
    Move-Item -Path $temporaryPath -Destination $StatusPath -Force
}

function Merge-UpdateLogs {
    $parts = @()
    if (Test-Path $StdoutPath -PathType Leaf) {
        $parts += Get-Content $StdoutPath -Raw
    }
    if (Test-Path $StderrPath -PathType Leaf) {
        $parts += Get-Content $StderrPath -Raw
    }

    [System.IO.File]::WriteAllText(
        $CombinedLogPath,
        ($parts -join "`r`n"),
        $Utf8NoBom
    )

    Remove-Item $StdoutPath, $StderrPath -Force -ErrorAction SilentlyContinue
}

try {
    if (-not (Test-Path $UpdaterScript -PathType Leaf)) {
        throw "DBAChum updater was not found: $UpdaterScript"
    }

    Write-UpdateStatus -State 'running' -Message "Installing DBAChum v$ReleaseVersion."

    $arguments = @(
        '-NoProfile',
        '-ExecutionPolicy',
        'Bypass',
        '-File',
        "`"$UpdaterScript`"",
        '-ReleaseVersion',
        $ReleaseVersion,
        '-Port',
        $Port.ToString(),
        '-TaskName',
        "`"$TaskName`"",
        '-TargetRoot',
        "`"$TargetRoot`""
    )

    if ($ValidateOnly) { $arguments += '-ValidateOnly' }
    if ($SkipDatabaseBackup) { $arguments += '-SkipDatabaseBackup' }
    if ($SkipSmoke) { $arguments += '-SkipSmoke' }
    if ($AllowSameVersion) { $arguments += '-AllowSameVersion' }

    $process = Start-Process `
        -FilePath 'powershell.exe' `
        -ArgumentList $arguments `
        -WorkingDirectory $TargetRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $StdoutPath `
        -RedirectStandardError $StderrPath `
        -Wait `
        -PassThru

    Merge-UpdateLogs

    if ($process.ExitCode -ne 0) {
        $rolledBack = $false
        if (Test-Path $CombinedLogPath -PathType Leaf) {
            $rolledBack = $null -ne (
                Select-String `
                    -Path $CombinedLogPath `
                    -Pattern 'rolled back successfully|Rollback restored DBAChum' `
                    -ErrorAction SilentlyContinue |
                Select-Object -First 1
            )
        }

        $state = if ($rolledBack) { 'failed_rolled_back' } else { 'failed' }
        $message = if ($rolledBack) {
            "DBAChum v$ReleaseVersion failed to install and the previous version was restored."
        }
        else {
            "DBAChum v$ReleaseVersion failed to install. Review the update log."
        }

        Write-UpdateStatus `
            -State $state `
            -Message $message `
            -FinishedAt ([DateTime]::UtcNow.ToString('o'))
        exit $process.ExitCode
    }

    $installedVersion = $null
    if (Test-Path $VersionFile -PathType Leaf) {
        $installedVersion = (Get-Content $VersionFile -Raw).Trim()
    }

    $successState = if ($ValidateOnly) { 'validated' } else { 'succeeded' }
    $successMessage = if ($ValidateOnly) {
        "DBAChum v$ReleaseVersion passed remote package validation."
    }
    else {
        "DBAChum v$ReleaseVersion installed successfully."
    }

    Write-UpdateStatus `
        -State $successState `
        -Message $successMessage `
        -FinishedAt ([DateTime]::UtcNow.ToString('o')) `
        -InstalledVersion $installedVersion
}
catch {
    try {
        Merge-UpdateLogs
    }
    catch {
    }

    Write-UpdateStatus `
        -State 'failed' `
        -Message "Unable to run the DBAChum update: $($_.Exception.Message)" `
        -FinishedAt ([DateTime]::UtcNow.ToString('o'))
    throw
}
