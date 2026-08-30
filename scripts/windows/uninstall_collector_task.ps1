param(
    [string]$TaskName = 'DBAChum Collector'
)

$ErrorActionPreference = 'Stop'

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Legacy standalone collector task '$TaskName' is not installed."
    Write-Host "The collector is managed by the main 'DBAChum' Scheduled Task."
    exit 0
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "PASS  Legacy standalone task '$TaskName' removed."
Write-Host "The collector is managed by the main 'DBAChum' Scheduled Task."
