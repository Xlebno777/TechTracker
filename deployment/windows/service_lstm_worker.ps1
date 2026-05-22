param([string]$AppRoot)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

$AppRoot = Get-TechTrackerRoot -AppRoot $AppRoot
Ensure-TechTrackerLogs -AppRoot $AppRoot
Import-TechTrackerEnv -AppRoot $AppRoot
Set-Location $AppRoot

if ($env:LSTM_REMOTE_CONFIGURED -ne "1") {
    Write-Host "LSTM remote is not configured. Worker will stay idle until integration is enabled in Settings -> Integrations."
    while ($true) {
        Start-Sleep -Seconds 300
        Import-TechTrackerEnv -AppRoot $AppRoot
        if ($env:LSTM_REMOTE_CONFIGURED -eq "1") {
            Write-Host "LSTM remote is now configured. Starting poll daemon."
            break
        }
    }
}

$Python = Get-TechTrackerPython -AppRoot $AppRoot
$Limit = if ($env:TECHTRACKER_LSTM_WORKER_LIMIT) { $env:TECHTRACKER_LSTM_WORKER_LIMIT } else { "20" }
$PollInterval = if ($env:TECHTRACKER_LSTM_WORKER_POLL_INTERVAL_SEC) { $env:TECHTRACKER_LSTM_WORKER_POLL_INTERVAL_SEC } else { "10" }
$IdleSleep = if ($env:TECHTRACKER_LSTM_WORKER_IDLE_SLEEP_SEC) { $env:TECHTRACKER_LSTM_WORKER_IDLE_SLEEP_SEC } else { "15" }

Write-Host "Starting LSTM remote poll daemon"
& $Python manage.py poll_forecast_lstm_remote --daemon --limit $Limit --poll-interval-sec $PollInterval --idle-sleep-sec $IdleSleep
$ExitCode = $LASTEXITCODE
if ($ExitCode -ne 0) {
    Write-Error "TechTracker LSTM worker stopped with exit code $ExitCode"
}
exit $ExitCode
