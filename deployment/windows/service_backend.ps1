param([string]$AppRoot)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$AppRoot = Get-TechTrackerRoot -AppRoot $AppRoot
Ensure-TechTrackerLogs -AppRoot $AppRoot
Import-TechTrackerEnv -AppRoot $AppRoot
Set-Location $AppRoot

$Python = Get-TechTrackerPython -AppRoot $AppRoot
$HostValue = if ($env:TECHTRACKER_BACKEND_HOST) { $env:TECHTRACKER_BACKEND_HOST } else { "0.0.0.0" }
$PortValue = if ($env:TECHTRACKER_BACKEND_PORT) { $env:TECHTRACKER_BACKEND_PORT } else { "8000" }
$Runner = Join-Path $PSScriptRoot "run_backend_waitress.py"

Write-Host "Starting TechTracker backend"
Write-Host "AppRoot=$AppRoot"
Write-Host "Python=$Python"
Write-Host "Listen=$HostValue`:$PortValue"

& $Python $Runner --app-root $AppRoot --host $HostValue --port $PortValue
$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    Write-Error "TechTracker backend stopped with exit code $ExitCode"
}
exit $ExitCode
