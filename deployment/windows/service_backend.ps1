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

& $Python -m waitress.runner --listen="$HostValue`:$PortValue" TechTracker_django.wsgi:application
