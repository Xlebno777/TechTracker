param([string]$AppRoot = "C:\TechTracker")

& (Join-Path $PSScriptRoot "winsw_services.ps1") -Action Uninstall -AppRoot $AppRoot
