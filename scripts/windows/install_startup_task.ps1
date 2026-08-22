param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$TaskName = 'DBAChum',

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
$RunScript = Join-Path $ProjectRoot 'scripts\windows\run_dbachum.ps1'

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
    -Description 'DBAChum FastAPI + Vue production server'

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
Write-Host "URL: http://localhost:$Port"
