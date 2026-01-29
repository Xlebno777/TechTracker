$ErrorActionPreference = 'Stop'

$taskName = 'TechTracker Server Agent'

try {
  Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
} catch {}

try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false | Out-Null
} catch {}
