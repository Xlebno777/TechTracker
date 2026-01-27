$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvActivate = Join-Path $root '.venv\Scripts\Activate.ps1'
$agentDir = Join-Path $root 'agents'
$clientPy = Join-Path $agentDir 'print_client.py'
$clientIni = Join-Path $agentDir 'print_client.ini'

if (!(Test-Path $venvActivate)) {
  Write-Error "Missing .venv. Create it with: python -m venv .venv"
}
if (!(Test-Path $clientPy)) {
  Write-Error "Missing agents/print_client.py"
}
if (!(Test-Path $clientIni)) {
  Write-Error "Missing agents/print_client.ini"
}

. $venvActivate
Set-Location $agentDir
python print_client.py
