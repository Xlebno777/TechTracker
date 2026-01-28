$ErrorActionPreference = 'Stop'

param(
  [string]$InstallDir
)

if (-not $InstallDir) {
  Write-Error "InstallDir is required."
}

$exe = Join-Path $InstallDir 'print_client.exe'
$ini = Join-Path $InstallDir 'print_client.ini'
$taskName = 'TechTracker Print Client'

if (!(Test-Path $exe)) { Write-Error "Missing $exe" }
if (!(Test-Path $ini)) { Write-Error "Missing $ini" }

$action = New-ScheduledTaskAction -Execute $exe -WorkingDirectory $InstallDir
$triggers = @(
  New-ScheduledTaskTrigger -AtStartup,
  New-ScheduledTaskTrigger -AtLogOn
)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
