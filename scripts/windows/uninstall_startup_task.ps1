param(
    [string]$TaskName = 'DBAChum',
    [string]$LegacyCollectorTaskName = 'DBAChum Collector'
)

$ErrorActionPreference = 'Stop'

$removed = $false

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -ne $task) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task '$TaskName'."
    $removed = $true
}

$legacyCollectorTask = Get-ScheduledTask -TaskName $LegacyCollectorTaskName -ErrorAction SilentlyContinue
if ($null -ne $legacyCollectorTask) {
    Stop-ScheduledTask -TaskName $LegacyCollectorTaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $LegacyCollectorTaskName -Confirm:$false
    Write-Host "Removed legacy standalone task '$LegacyCollectorTaskName'."
    $removed = $true
}

if (-not $removed) {
    Write-Host "DBAChum startup automation is not installed."
}
