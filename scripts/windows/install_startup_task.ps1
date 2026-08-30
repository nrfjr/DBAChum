param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$TaskName = 'DBAChum',

    [string]$LegacyCollectorTaskName = 'DBAChum Collector',

    [switch]$OpenFirewall,

    [string[]]$FirewallRemoteAddress = @('LocalSubnet')
)

$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principalCheck = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principalCheck.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this script from an elevated PowerShell window (Run as Administrator).'
}

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$RunScript = Join-Path $ProjectRoot 'scripts\windows\run_dbachum_stack.ps1'

if (-not (Test-Path $RunScript)) {
    throw "DBAChum stack launcher was not found: $RunScript"
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask -and $existingTask.State -eq 'Running') {
    Write-Host "Stopping existing scheduled task '$TaskName' before upgrading it..."
    Stop-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
}

# Phase 6A originally installed the collector as a second Scheduled Task.
# The stack supervisor now owns both processes. Remove the old task first so
# upgrading an existing machine cannot accidentally run two collectors.
$legacyCollectorTask = Get-ScheduledTask -TaskName $LegacyCollectorTaskName -ErrorAction SilentlyContinue
if ($null -ne $legacyCollectorTask) {
    Stop-ScheduledTask -TaskName $LegacyCollectorTaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $LegacyCollectorTaskName -Confirm:$false
    Write-Host "Removed legacy standalone task '$LegacyCollectorTaskName'."
}

$actionArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$RunScript`" -Port $Port"
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
    -Description 'DBAChum stack supervisor: FastAPI + Vue server and background telemetry collector'

Register-ScheduledTask `
    -TaskName $TaskName `
    -InputObject $task `
    -Force | Out-Null

if ($OpenFirewall) {
    $ruleName = "DBAChum TCP $Port"
    $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if ($null -ne $existingRule) {
        Remove-NetFirewallRule -DisplayName $ruleName
    }

    New-NetFirewallRule `
        -DisplayName $ruleName `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort $Port `
        -Profile Domain,Private `
        -RemoteAddress $FirewallRemoteAddress | Out-Null

    Write-Host (
        "Windows Firewall allows TCP $Port from: " +
        ($FirewallRemoteAddress -join ', ')
    )
}

Start-ScheduledTask -TaskName $TaskName
Write-Host "PASS  Scheduled task '$TaskName' installed and started."
Write-Host '      Web server and telemetry collector now share one start/stop/restart lifecycle.'
Write-Host "URL: http://localhost:$Port"
Write-Host 'Logs: logs\dbachum-stack.log, logs\dbachum-server.log, logs\dbachum-collector.log'
