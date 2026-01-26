$ErrorActionPreference = 'Stop'

$env:PGCLIENTENCODING='UTF8'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envFile = Join-Path $root '.env.local'
$venvActivate = Join-Path $root '.venv\Scripts\Activate.ps1'

if (!(Test-Path $envFile)) {
  Write-Error "Missing .env.local in project root"
}
if (!(Test-Path $venvActivate)) {
  Write-Error "Missing .venv. Create it with: python -m venv .venv"
}

Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
    $name = $Matches[1]
    $value = $Matches[2].Trim()
    if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
      $value = $value.Substring(1, $value.Length - 2)
    }
    [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
  }
}

. $venvActivate

Set-Location $root
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
