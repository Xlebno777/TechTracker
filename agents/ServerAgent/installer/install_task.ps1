$ErrorActionPreference = 'Stop'

param(
  [string]$InstallDir
)

if (-not $InstallDir) {
  Write-Error "InstallDir is required."
}

$exe = Join-Path $InstallDir 'TechTrackerAgent.exe'
$ini = Join-Path $InstallDir 'config.ini'
$taskName = 'TechTracker Server Agent'

if (!(Test-Path $exe)) { Write-Error "Missing $exe" }
if (!(Test-Path $ini)) { Write-Error "Missing $ini" }

$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory $InstallDir
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
