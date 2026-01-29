$ErrorActionPreference = 'Stop'

$installDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskName = 'TechTracker Server Agent'

try {
  Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue | Out-Null
} catch {}

try {
  Unregister-ScheduledTask -TaskName $taskName -Confirm:$false | Out-Null
} catch {}

try {
  Get-Process -Name 'TechTrackerAgent' -ErrorAction SilentlyContinue | Stop-Process -Force
} catch {}

try {
  $cmd = "/c timeout /t 2 >nul & rmdir /s /q \"$installDir\""
  Start-Process -FilePath cmd.exe -ArgumentList $cmd -WindowStyle Hidden
} catch {}
