param([string]$AppRoot)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$AppRoot = Get-TechTrackerRoot -AppRoot $AppRoot
Ensure-TechTrackerLogs -AppRoot $AppRoot
Import-TechTrackerEnv -AppRoot $AppRoot
Set-Location $AppRoot

$Node = if ($env:TECHTRACKER_NODE_EXE) { $env:TECHTRACKER_NODE_EXE } else { "node" }
$Port = if ($env:TECHTRACKER_FRONTEND_PORT) { $env:TECHTRACKER_FRONTEND_PORT } else { "8080" }
$BackendUrl = if ($env:TECHTRACKER_BACKEND_URL) { $env:TECHTRACKER_BACKEND_URL } else { "http://127.0.0.1:8000" }
$DistDir = if ($env:TECHTRACKER_FRONTEND_DIST) { $env:TECHTRACKER_FRONTEND_DIST } else { Join-Path $AppRoot "techtracker_vue\dist" }

& $Node (Join-Path $PSScriptRoot "static_server.js") --port $Port --backend $BackendUrl --dist $DistDir
