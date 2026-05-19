param(
    [string]$AppRoot = "C:\TechTracker",
    [switch]$Start
)

& (Join-Path $PSScriptRoot "winsw_services.ps1") -Action Install -AppRoot $AppRoot -StartAfterInstall:$Start
