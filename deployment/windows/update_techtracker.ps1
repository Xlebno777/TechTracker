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
    # PowerShell 5.1 can treat native command stderr/progress as a
    # NativeCommandError when ErrorActionPreference=Stop and streams are
    # redirected into Tee-Object. Git writes normal progress like
    # "Cloning into ..." to stderr, so the update could fail even when git
    # eventually exits with code 0. During a step we capture all streams as
    # text and let explicit exit-code checks inside the block decide failure.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $Block *>&1
        foreach ($item in @($output)) {
            $line = [string]$item
            if (-not [string]::IsNullOrWhiteSpace($line)) {
                Write-Host $line
                Add-Content -Path $LogFile -Value $line -Encoding UTF8
            }
        }
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
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

function Get-BackendBaseUrl {
    $raw = $env:TECHTRACKER_BACKEND_URL
    if ([string]::IsNullOrWhiteSpace($raw)) {
        $port = if ($env:TECHTRACKER_BACKEND_PORT) { $env:TECHTRACKER_BACKEND_PORT } else { "8000" }
        return "http://127.0.0.1:$port"
    }

    try {
        $builder = New-Object System.UriBuilder($raw)
        if ($builder.Host -eq "0.0.0.0" -or $builder.Host -eq "::" -or $builder.Host -eq "*") {
            $builder.Host = "127.0.0.1"
        }
        return $builder.Uri.AbsoluteUri.TrimEnd("/")
    } catch {
        $port = if ($env:TECHTRACKER_BACKEND_PORT) { $env:TECHTRACKER_BACKEND_PORT } else { "8000" }
        return "http://127.0.0.1:$port"
    }
}

function Wait-ServiceState {
    param(
        [string]$Name,
        [string]$Desired,
        [int]$TimeoutSec = 45
    )
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
        if (-not $svc) {
            return $false
        }
        if ([string]$svc.Status -eq $Desired) {
            return $true
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    $current = if ($svc) { [string]$svc.Status } else { "not installed" }
    throw "Сервис $Name не перешел в состояние $Desired за $TimeoutSec сек. Текущее состояние: $current"
}

function Test-BackendStopped {
    param(
        [string]$BaseUrl,
        [int]$TimeoutSec = 25
    )
    $healthUrl = "$BaseUrl/api/health/"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    do {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Step "Backend все еще отвечает на $healthUrl после Stop-Service, жду освобождения порта..."
                Start-Sleep -Seconds 2
                continue
            }
        } catch {
            return
        }
    } while ((Get-Date) -lt $deadline)

    throw "Backend все еще отвечает на $healthUrl через $TimeoutSec сек. после остановки сервиса. Вероятно, на порту работает старый ручной/stale Python-процесс, поэтому новые URLConf не загрузятся."
}

function Wait-BackendReady {
    param(
        [string]$BaseUrl,
        [string]$ExpectedVersion,
        [int]$TimeoutSec = 90
    )
    $healthUrl = "$BaseUrl/api/health/?detail=1"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    $lastMessage = ""

    do {
        try {
            $response = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 8
            $payload = $response.Content | ConvertFrom-Json
            $appVersion = [string]$payload.app_version
            $routeOk = [bool]$payload.agent_installer_status_route_registered
            $versionOk = $true
            if (-not [string]::IsNullOrWhiteSpace($ExpectedVersion)) {
                $versionOk = ($appVersion.TrimStart([char[]]"vV") -eq $ExpectedVersion.TrimStart([char[]]"vV"))
            }

            if ($payload.status -eq "ok" -and $routeOk -and $versionOk) {
                Write-Step "Backend health OK. app_version=$appVersion pid=$($payload.process_id) agent_installer_route=$routeOk"
                return
            }

            $lastMessage = "health ответил, но backend еще не готов: app_version=$appVersion expected=$ExpectedVersion agent_installer_route=$routeOk pid=$($payload.process_id)"
            Write-Step $lastMessage
        } catch {
            $lastMessage = $_.Exception.Message
            Write-Step "Ожидание backend health: $lastMessage"
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    throw "Backend не подтвердил новую версию и agent installer route за $TimeoutSec сек. Последняя проверка: $lastMessage"
}

function Assert-EndpointNot404 {
    param(
        [string]$Url,
        [string]$Name
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        Write-Step "$Name endpoint ответил HTTP $($response.StatusCode): $Url"
        return
    } catch {
        $response = $_.Exception.Response
        if (-not $response) {
            throw "$Name endpoint не ответил: $Url. Ошибка: $($_.Exception.Message)"
        }
        $statusCode = [int]$response.StatusCode
        if ($statusCode -eq 404) {
            throw "$Name endpoint вернул HTTP 404: $Url. Это значит, что запущенный backend не загрузил новый URLConf."
        }
        if ($statusCode -eq 401 -or $statusCode -eq 403) {
            Write-Step "$Name endpoint найден и защищен авторизацией: HTTP $statusCode $Url"
            return
        }
        if ($statusCode -ge 500) {
            throw "$Name endpoint вернул HTTP $statusCode: $Url"
        }
        Write-Step "$Name endpoint ответил HTTP $statusCode: $Url"
    }
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
$BackendBaseUrl = Get-BackendBaseUrl

if ($LstmWorkerService) {
    Invoke-Step "Stopping LSTM worker service $LstmWorkerService" {
        if (Get-Service -Name $LstmWorkerService -ErrorAction SilentlyContinue) {
            Stop-Service -Name $LstmWorkerService -ErrorAction Stop
            Wait-ServiceState -Name $LstmWorkerService -Desired "Stopped" -TimeoutSec 45 | Out-Null
        }
    }
}
if ($BackendService) {
    Invoke-Step "Stopping backend service $BackendService" {
        if (Get-Service -Name $BackendService -ErrorAction SilentlyContinue) {
            Stop-Service -Name $BackendService -ErrorAction Stop
            Wait-ServiceState -Name $BackendService -Desired "Stopped" -TimeoutSec 60 | Out-Null
        }
    }
    Invoke-Step "Verifying backend process stopped" {
        Test-BackendStopped -BaseUrl $BackendBaseUrl
    }
}
if ($FrontendService) {
    Invoke-Step "Stopping frontend service $FrontendService" {
        if (Get-Service -Name $FrontendService -ErrorAction SilentlyContinue) {
            Stop-Service -Name $FrontendService -ErrorAction Stop
            Wait-ServiceState -Name $FrontendService -Desired "Stopped" -TimeoutSec 45 | Out-Null
        }
    }
}

$TempRoot = Join-Path $env:TEMP "TechTrackerUpdate_$Stamp"

try {
    Invoke-Step "Cloning update source" {
        if (Test-Path $TempRoot) { Remove-Item -Recurse -Force $TempRoot }
        git clone --quiet $RepoUrl $TempRoot
        if ($LASTEXITCODE -ne 0) { throw "git clone завершился с кодом $LASTEXITCODE" }
    }

    Push-Location $TempRoot
    try {
        if (-not [string]::IsNullOrWhiteSpace($GitRef)) {
            Invoke-Step "Checking out $GitRef" {
                git -c advice.detachedHead=false checkout --quiet $GitRef
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
    if ([string]::IsNullOrWhiteSpace($TargetVersion) -and (Test-Path "VERSION")) {
        $TargetVersion = ((Get-Content "VERSION" -Raw) -as [string]).Trim()
    }
    Invoke-Step "Updating release settings in .env.local" {
        if (-not [string]::IsNullOrWhiteSpace($TargetVersion)) {
            Set-EnvFileValue -Path (Join-Path $AppRoot ".env.local") -Key "APP_VERSION" -Value $TargetVersion
        }
        Set-EnvFileValue -Path (Join-Path $AppRoot ".env.local") -Key "TECHTRACKER_REPO_URL" -Value $RepoUrl
        Set-EnvFileValue -Path (Join-Path $AppRoot ".env.local") -Key "APP_RELEASE_MANIFEST_URL" -Value "https://api.github.com/repos/Xlebno777/TechTracker/releases/latest"
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

    Invoke-Step "Verifying agent API routes" {
        & $Python -c "import os; os.environ.setdefault('DJANGO_SETTINGS_MODULE','TechTracker_django.settings'); import django; django.setup(); from django.urls import resolve; [resolve(path) for path in ('/api/agent-installer/','/api/installers/agent/','/api/agents/','/api/agents/metric-catalog/','/api/application-updates/agent-installer/')]; print('agent API routes OK')"
        if ($LASTEXITCODE -ne 0) { throw "Проверка agent API routes завершилась с кодом $LASTEXITCODE" }
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
                Wait-ServiceState -Name $BackendService -Desired "Running" -TimeoutSec 60 | Out-Null
            }
        }
        Invoke-Step "Verifying running backend routes" {
            Wait-BackendReady -BaseUrl $BackendBaseUrl -ExpectedVersion $TargetVersion -TimeoutSec 90
            Assert-EndpointNot404 -Url "$BackendBaseUrl/api/agent-installer/" -Name "Agent installer"
            Assert-EndpointNot404 -Url "$BackendBaseUrl/api/agents/" -Name "Agents"
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
