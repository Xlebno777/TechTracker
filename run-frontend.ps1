$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$front = Join-Path $root 'techtracker_vue'

if (!(Test-Path $front)) {
  Write-Error "Missing techtracker_vue folder"
}

Set-Location $front

if (!(Test-Path (Join-Path $front 'node_modules'))) {
  npm install
}

npm run serve
