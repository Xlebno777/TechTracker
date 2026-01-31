$ErrorActionPreference = 'Stop'

$taskName = 'TechTracker Compute Derived Metrics'

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
  Write-Host "Scheduled task '$taskName' removed."
} else {
  Write-Host "Scheduled task '$taskName' not found."
}
