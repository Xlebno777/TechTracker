param([string]$AppRoot)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$AppRoot = Get-TechTrackerRoot -AppRoot $AppRoot
Ensure-TechTrackerLogs -AppRoot $AppRoot
Import-TechTrackerEnv -AppRoot $AppRoot
Set-Location $AppRoot

$Python = Get-TechTrackerPython -AppRoot $AppRoot
$Limit = if ($env:TECHTRACKER_LSTM_WORKER_LIMIT) { $env:TECHTRACKER_LSTM_WORKER_LIMIT } else { "20" }
$PollInterval = if ($env:TECHTRACKER_LSTM_WORKER_POLL_INTERVAL_SEC) { $env:TECHTRACKER_LSTM_WORKER_POLL_INTERVAL_SEC } else { "10" }
$IdleSleep = if ($env:TECHTRACKER_LSTM_WORKER_IDLE_SLEEP_SEC) { $env:TECHTRACKER_LSTM_WORKER_IDLE_SLEEP_SEC } else { "15" }

& $Python manage.py poll_forecast_lstm_remote --daemon --limit $Limit --poll-interval-sec $PollInterval --idle-sleep-sec $IdleSleep
