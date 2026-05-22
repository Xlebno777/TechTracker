param(
    [string]$AppRoot = $env:TECHTRACKER_APP_ROOT,
    [string]$JobId = $env:TECHTRACKER_UPDATE_JOB_ID,
    [string]$GitRef = $env:TECHTRACKER_TARGET_REF,
    [string]$TargetVersion = $env:TECHTRACKER_TARGET_VERSION,
    [string]$RepoUrl = $env:TECHTRACKER_REPO_URL
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoUrl)) {
    $RepoUrl = "https://github.com/Xlebno777/TechTracker.git"
}
if ([string]::IsNullOrWhiteSpace($AppRoot)) {
    $AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$AppRoot = (Resolve-Path $AppRoot).Path
$LogRoot = Join-Path $AppRoot "logs"
$BackupRoot = Join-Path $AppRoot "backups"
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogRoot "update_$Stamp`_$JobId.log"

function Write-Step {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    Write-Step $Name
    & $Block *>&1 | Tee-Object -FilePath $LogFile -Append
}

function Copy-TechTrackerSource {
    param(
        [string]$SourceRoot,
        [string]$TargetRoot
    )
    $source = (Resolve-Path $SourceRoot).Path
    $target = (Resolve-Path $TargetRoot).Path
    if (Get-Command "robocopy" -ErrorAction SilentlyContinue) {
        $args = @(
            $source,
            $target,
            "/E",
            "/XD", ".git", ".venv", "node_modules", "__pycache__", ".idea", ".vscode", "logs", "backups", "dist",
            "/XF", ".env.local", ".env", "*.pyc", "*.pyo", "*.log"
        )
        & robocopy @args | Tee-Object -FilePath $LogFile -Append
        if ($LASTEXITCODE -gt 7) {
            throw "robocopy завершился с кодом $LASTEXITCODE"
        }
    } else {
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    }
}

function Set-EnvFileValue {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content $Path)
    }
    $escaped = ([string]$Value).Replace('\', '\\').Replace('"', '\"')
    $line = "${Key}=`"$escaped`""
    $found = $false
    $updated = foreach ($existing in $lines) {
        if ($existing -match "^\s*(export\s+)?$([Regex]::Escape($Key))\s*=") {
            $found = $true
            $line
        } else {
            $existing
        }
    }
    if (-not $found) {
        $updated += $line
    }
    Set-Content -Path $Path -Value $updated -Encoding UTF8
}

function Get-PythonExecutable {
    if (Test-Path ".venv\Scripts\python.exe") {
        return ".venv\Scripts\python.exe"
    }
    return "python"
}

Write-Step "TechTracker update started. JobId=$JobId TargetVersion=$TargetVersion GitRef=$GitRef RepoUrl=$RepoUrl AppRoot=$AppRoot"
Set-Location $AppRoot

$CurrentCommit = ""
try {
    if (Test-Path ".git") {
        $CurrentCommit = (git rev-parse HEAD).Trim()
        Write-Step "Current git commit: $CurrentCommit"
    } else {
        Write-Step "Current installation has no .git directory; update will use temporary clone."
    }
} catch {
    Write-Step "Current git commit is unknown: $($_.Exception.Message)"
}

$BackupDir = Join-Path $BackupRoot "before_update_$Stamp"
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
if (Test-Path ".env.local") {
    Copy-Item ".env.local" (Join-Path $BackupDir ".env.local") -Force
}
if ($CurrentCommit) {
    Set-Content -Path (Join-Path $BackupDir "git_commit.txt") -Value $CurrentCommit -Encoding UTF8
}

$BackendService = if ($env:TECHTRACKER_BACKEND_SERVICE) { $env:TECHTRACKER_BACKEND_SERVICE } else { "TechTrackerBackend" }
$FrontendService = if ($env:TECHTRACKER_FRONTEND_SERVICE) { $env:TECHTRACKER_FRONTEND_SERVICE } else { "TechTrackerFrontend" }
$LstmWorkerService = if ($env:TECHTRACKER_LSTM_WORKER_SERVICE) { $env:TECHTRACKER_LSTM_WORKER_SERVICE } else { "TechTrackerLSTMWorker" }

if ($LstmWorkerService) {
    Invoke-Step "Stopping LSTM worker service $LstmWorkerService" {
        if (Get-Service -Name $LstmWorkerService -ErrorAction SilentlyContinue) {
            Stop-Service -Name $LstmWorkerService -ErrorAction SilentlyContinue
        }
    }
}
if ($BackendService) {
    Invoke-Step "Stopping backend service $BackendService" {
        if (Get-Service -Name $BackendService -ErrorAction SilentlyContinue) {
            Stop-Service -Name $BackendService -ErrorAction SilentlyContinue
        }
    }
}
if ($FrontendService) {
    Invoke-Step "Stopping frontend service $FrontendService" {
        if (Get-Service -Name $FrontendService -ErrorAction SilentlyContinue) {
            Stop-Service -Name $FrontendService -ErrorAction SilentlyContinue
        }
    }
}

$TempRoot = Join-Path $env:TEMP "TechTrackerUpdate_$Stamp"

try {
    Invoke-Step "Cloning update source" {
        if (Test-Path $TempRoot) { Remove-Item -Recurse -Force $TempRoot }
        git clone $RepoUrl $TempRoot
        if ($LASTEXITCODE -ne 0) { throw "git clone завершился с кодом $LASTEXITCODE" }
    }

    Push-Location $TempRoot
    try {
        if (-not [string]::IsNullOrWhiteSpace($GitRef)) {
            Invoke-Step "Checking out $GitRef" {
                git checkout $GitRef
                if ($LASTEXITCODE -ne 0) { throw "git checkout $GitRef завершился с кодом $LASTEXITCODE" }
            }
        } else {
            Invoke-Step "Using default repository branch" {
                git status --short
            }
        }
    } finally {
        Pop-Location
    }

    Invoke-Step "Copying updated source into AppRoot" {
        Copy-TechTrackerSource -SourceRoot $TempRoot -TargetRoot $AppRoot
    }

    Set-Location $AppRoot
    if (-not [string]::IsNullOrWhiteSpace($TargetVersion)) {
        Invoke-Step "Updating APP_VERSION in .env.local" {
            Set-EnvFileValue -Path (Join-Path $AppRoot ".env.local") -Key "APP_VERSION" -Value $TargetVersion
            Set-EnvFileValue -Path (Join-Path $AppRoot ".env.local") -Key "TECHTRACKER_REPO_URL" -Value $RepoUrl
            Set-EnvFileValue -Path (Join-Path $AppRoot ".env.local") -Key "APP_RELEASE_MANIFEST_URL" -Value "https://api.github.com/repos/Xlebno777/TechTracker/releases/latest"
        }
    }

    $Python = Get-PythonExecutable

    Invoke-Step "Installing backend requirements" {
        & $Python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "pip install завершился с кодом $LASTEXITCODE" }
    }

    Invoke-Step "Applying Django migrations" {
        & $Python manage.py migrate --noinput
        if ($LASTEXITCODE -ne 0) { throw "manage.py migrate завершился с кодом $LASTEXITCODE" }
    }

    if (Test-Path "techtracker_vue\package.json") {
        Push-Location "techtracker_vue"
        try {
            Invoke-Step "Installing frontend packages" {
                npm ci
                if ($LASTEXITCODE -ne 0) { throw "npm ci завершился с кодом $LASTEXITCODE" }
            }
            Invoke-Step "Building frontend" {
                npm run build
                if ($LASTEXITCODE -ne 0) { throw "npm run build завершился с кодом $LASTEXITCODE" }
            }
        } finally {
            Pop-Location
        }
    }

    if (Test-Path "deployment\windows\winsw_services.ps1") {
        Invoke-Step "Reinstalling WinSW services configuration" {
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File "deployment\windows\winsw_services.ps1" -Action Reinstall -AppRoot $AppRoot
            if ($LASTEXITCODE -ne 0) { throw "winsw_services.ps1 завершился с кодом $LASTEXITCODE" }
        }
    }

    if ($BackendService) {
        Invoke-Step "Starting backend service $BackendService" {
            if (Get-Service -Name $BackendService -ErrorAction SilentlyContinue) {
                Start-Service -Name $BackendService
            }
        }
    }
    if ($FrontendService) {
        Invoke-Step "Starting frontend service $FrontendService" {
            if (Get-Service -Name $FrontendService -ErrorAction SilentlyContinue) {
                Start-Service -Name $FrontendService
            }
        }
    }
    if ($LstmWorkerService) {
        Invoke-Step "Starting LSTM worker service $LstmWorkerService" {
            if (Get-Service -Name $LstmWorkerService -ErrorAction SilentlyContinue) {
                Start-Service -Name $LstmWorkerService
            }
        }
    }

    Write-Step "TechTracker update completed successfully."
    exit 0
} catch {
    Write-Step "Update failed: $($_.Exception.Message)"
    if ($BackendService) { try { Start-Service -Name $BackendService } catch {} }
    if ($FrontendService) { try { Start-Service -Name $FrontendService } catch {} }
    if ($LstmWorkerService) { try { Start-Service -Name $LstmWorkerService } catch {} }
    exit 1
} finally {
    try {
        if (Test-Path $TempRoot) { Remove-Item -Recurse -Force $TempRoot }
    } catch {}
}
