param(
    [string]$TaskName = 'DBAChum Collector'
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell window (Run as Administrator).'
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RunScript = Join-Path $ProjectRoot 'scripts\windows\run_collector.ps1'

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`""
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument $actionArgs `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal `
    -UserId 'SYSTEM' `
    -LogonType ServiceAccount `
    -RunLevel Highest

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew

$task = New-ScheduledTask `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description 'DBAChum Phase 6 background telemetry collector (rolling 24-hour history)'

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -Force | Out-Null

Start-ScheduledTask -TaskName $TaskName
Write-Host "PASS  Scheduled task '$TaskName' installed and started."
Write-Host 'Collector log: logs\dbachum-collector.log'
