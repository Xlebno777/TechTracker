param([string]$AppRoot = "C:\TechTracker")

& (Join-Path $PSScriptRoot "winsw_services.ps1") -Action Restart -AppRoot $AppRoot
