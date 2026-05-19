param(
    [string]$AppRoot = "C:\TechTracker",
    [string]$Python = "python",
    [switch]$SkipFrontendBuild,
    [switch]$InstallServices,
    [switch]$StartServices
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $AppRoot)) {
    throw "AppRoot not found: $AppRoot"
}

Set-Location $AppRoot

if (-not (Test-Path ".env.local")) {
    throw ".env.local is missing. Create it before installation."
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $Python -m venv .venv
}

$VenvPython = ".venv\Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt
& $VenvPython manage.py migrate --noinput
& $VenvPython manage.py collectstatic --noinput

if (-not $SkipFrontendBuild -and (Test-Path "techtracker_vue\package.json")) {
    Push-Location "techtracker_vue"
    try {
        npm ci
        npm run build
    } finally {
        Pop-Location
    }
}

Write-Host "TechTracker base installation finished."

if ($InstallServices) {
    & (Join-Path $PSScriptRoot "winsw_services.ps1") -Action Install -AppRoot $AppRoot -StartAfterInstall:$StartServices
} else {
    Write-Host "Next: run deployment\windows\install_winsw_services.ps1 -AppRoot $AppRoot -Start"
}
