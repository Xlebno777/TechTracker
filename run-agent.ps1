$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvActivate = Join-Path $root '.venv\Scripts\Activate.ps1'
$agentDir = Join-Path $root 'agents'
$agentPy = Join-Path $agentDir 'agent_server.py'

if (!(Test-Path $venvActivate)) {
  Write-Error "Missing .venv. Create it with: python -m venv .venv"
}
if (!(Test-Path $agentPy)) {
  Write-Error "Missing agents/agent_server.py"
}

. $venvActivate

Set-Location $agentDir
python agent_server.py
