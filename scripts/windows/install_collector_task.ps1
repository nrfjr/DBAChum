param(
    [ValidateRange(1, 65535)]
    [int]$Port = 8080,

    [string]$TaskName = 'DBAChum Collector'
)

$ErrorActionPreference = 'Stop'

Write-Warning "The standalone collector task '$TaskName' is retired. The collector is now supervised by the main DBAChum task so web + telemetry start and stop together."
Write-Host 'Installing/upgrading the unified DBAChum startup task instead...'

$installer = Join-Path $PSScriptRoot 'install_startup_task.ps1'
& $installer -Port $Port
