param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+\.[0-9]+\.[0-9]+$')]
    [string]$ReleaseVersion,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-f]{12,32}$')]
    [string]$UpdateId,

    [string]$TargetRoot = '',

    [string]$TaskName = 'DBAChum',

    [string]$UpdaterTaskName = 'DBAChum-Updater',

    [switch]$ValidateOnly,
    [switch]$SkipDatabaseBackup,
    [switch]$SkipSmoke,
    [switch]$AllowSameVersion
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Quote-TaskArgument([string]$Value) {
    if ($Value.Contains('"')) {
        throw 'Scheduled-task arguments cannot contain a double quote.'
    }
    return '"' + $Value + '"'
}

function Write-QueuedStatus([string]$StatusPath, [string]$LogFile) {
    $document = [ordered]@{
        update_id = $UpdateId
        state = 'queued'
        requested_version = $ReleaseVersion
        installed_version = $null
        created_at = [DateTime]::UtcNow.ToString('o')
        started_at = $null
        finished_at = $null
        message = "DBAChum v$ReleaseVersion update is queued."
        log_file = $LogFile
    }

    $temporaryPath = "$StatusPath.$PID.tmp"
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        ($document | ConvertTo-Json -Depth 4),
        $Utf8NoBom
    )
    Move-Item -Path $temporaryPath -Destination $StatusPath -Force
}

if (-not (Test-IsAdministrator)) {
    throw 'DBAChum in-app updates must be queued by an elevated DBAChum service account.'
}

if ([string]::IsNullOrWhiteSpace($TargetRoot)) {
    $TargetRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
}
else {
    $TargetRoot = [System.IO.Path]::GetFullPath($TargetRoot)
}

$RunnerScript = Join-Path $TargetRoot 'scripts\windows\run_update_task.ps1'
$UpdaterScript = Join-Path $TargetRoot 'scripts\windows\update_dbachum.ps1'
$UpdateRoot = Join-Path $TargetRoot '.update'
$LogRoot = Join-Path $UpdateRoot 'logs'
$StatusPath = Join-Path $UpdateRoot 'status.json'
$RelativeLog = ".update/logs/update-$UpdateId.log"

foreach ($required in @($RunnerScript, $UpdaterScript)) {
    if (-not (Test-Path $required -PathType Leaf)) {
        throw "Required DBAChum update script was not found: $required"
    }
}

$mainTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $mainTask) {
    throw "DBAChum scheduled task '$TaskName' was not found. Install the normal DBAChum startup task before using in-app updates."
}

$existingUpdaterTask = Get-ScheduledTask -TaskName $UpdaterTaskName -ErrorAction SilentlyContinue
if ($null -ne $existingUpdaterTask -and $existingUpdaterTask.State -eq 'Running') {
    throw "DBAChum updater task '$UpdaterTaskName' is already running."
}
if ($null -ne $existingUpdaterTask) {
    Unregister-ScheduledTask -TaskName $UpdaterTaskName -Confirm:$false
}

$Port = 8080
foreach ($actionItem in @($mainTask.Actions)) {
    $argumentsText = [string]$actionItem.Arguments
    $portMatch = [regex]::Match($argumentsText, '(?i)(?:^|\s)-Port\s+(?<port>[0-9]{1,5})(?:\s|$)')
    if ($portMatch.Success) {
        $candidate = [int]$portMatch.Groups['port'].Value
        if ($candidate -ge 1 -and $candidate -le 65535) {
            $Port = $candidate
            break
        }
    }
}

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
Write-QueuedStatus $StatusPath $RelativeLog

$actionArguments = @(
    '-NoProfile',
    '-ExecutionPolicy',
    'Bypass',
    '-File',
    (Quote-TaskArgument $RunnerScript),
    '-ReleaseVersion',
    $ReleaseVersion,
    '-UpdateId',
    $UpdateId,
    '-TargetRoot',
    (Quote-TaskArgument $TargetRoot),
    '-Port',
    $Port.ToString(),
    '-TaskName',
    (Quote-TaskArgument $TaskName)
)

if ($ValidateOnly) { $actionArguments += '-ValidateOnly' }
if ($SkipDatabaseBackup) { $actionArguments += '-SkipDatabaseBackup' }
if ($SkipSmoke) { $actionArguments += '-SkipSmoke' }
if ($AllowSameVersion) { $actionArguments += '-AllowSameVersion' }

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ($actionArguments -join ' ') `
    -WorkingDirectory $TargetRoot

$principal = New-ScheduledTaskPrincipal `
    -UserId 'SYSTEM' `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask `
        -TaskName $UpdaterTaskName `
        -Action $action `
        -Principal $principal `
        -Settings $settings `
        -Description 'DBAChum one-shot in-app release updater' `
        -Force | Out-Null

    Start-ScheduledTask -TaskName $UpdaterTaskName
}
catch {
    $failed = [ordered]@{
        update_id = $UpdateId
        state = 'failed'
        requested_version = $ReleaseVersion
        installed_version = $null
        created_at = [DateTime]::UtcNow.ToString('o')
        started_at = $null
        finished_at = [DateTime]::UtcNow.ToString('o')
        message = "Unable to queue the DBAChum update: $($_.Exception.Message)"
        log_file = $RelativeLog
    }
    $temporaryPath = "$StatusPath.$PID.tmp"
    [System.IO.File]::WriteAllText(
        $temporaryPath,
        ($failed | ConvertTo-Json -Depth 4),
        $Utf8NoBom
    )
    Move-Item -Path $temporaryPath -Destination $StatusPath -Force
    throw
}

Write-Host "PASS  Queued DBAChum v$ReleaseVersion as update $UpdateId using scheduled task '$UpdaterTaskName'."
