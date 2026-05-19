param(
    [string]$AppRoot = $env:TECHTRACKER_APP_ROOT,
    [string]$JobId = $env:TECHTRACKER_UPDATE_JOB_ID,
    [string]$GitRef = $env:TECHTRACKER_TARGET_REF,
    [string]$TargetVersion = $env:TECHTRACKER_TARGET_VERSION
)

$ErrorActionPreference = "Stop"

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

Write-Step "TechTracker update started. JobId=$JobId TargetVersion=$TargetVersion GitRef=$GitRef AppRoot=$AppRoot"
Set-Location $AppRoot

$CurrentCommit = ""
try {
    $CurrentCommit = (git rev-parse HEAD).Trim()
    Write-Step "Current git commit: $CurrentCommit"
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

try {
    Invoke-Step "Fetching git updates" {
        git fetch --all --tags --prune
    }

    if (-not [string]::IsNullOrWhiteSpace($GitRef)) {
        Invoke-Step "Checking out $GitRef" {
            git checkout $GitRef
        }
    } else {
        Invoke-Step "Pulling current branch with fast-forward only" {
            git pull --ff-only
        }
    }

    if (Test-Path ".venv\Scripts\python.exe") {
        $Python = ".venv\Scripts\python.exe"
    } else {
        $Python = "python"
    }

    Invoke-Step "Installing backend requirements" {
        & $Python -m pip install -r requirements.txt
    }

    Invoke-Step "Applying Django migrations" {
        & $Python manage.py migrate --noinput
    }

    if (Test-Path "techtracker_vue\package.json") {
        Push-Location "techtracker_vue"
        try {
            Invoke-Step "Installing frontend packages" {
                npm ci
            }
            Invoke-Step "Building frontend" {
                npm run build
            }
        } finally {
            Pop-Location
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
    if ($BackendService) {
        try { Start-Service -Name $BackendService } catch {}
    }
    if ($FrontendService) {
        try { Start-Service -Name $FrontendService } catch {}
    }
    if ($LstmWorkerService) {
        try { Start-Service -Name $LstmWorkerService } catch {}
    }
    exit 1
}
