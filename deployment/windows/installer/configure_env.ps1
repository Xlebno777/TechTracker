function Read-TechTrackerInstallConfig {
    param(
        [string]$AppRoot,
        [string]$RepoUrl,
        [string]$GitRef,
        [switch]$AssumeDefaults
    )
    $hostname = try { [System.Net.Dns]::GetHostName() } catch { "localhost" }
    $versionPath = Join-Path $AppRoot "VERSION"
    $appVersion = if (Test-Path $versionPath) { (Get-Content $versionPath -Raw).Trim() } else { "0.1.0" }

    if ($AssumeDefaults) {
        $dbPassword = New-TechTrackerSecret 24
        $adminPassword = New-TechTrackerSecret 18
        $lstmToken = New-TechTrackerSecret 32
        return @{
            AppRoot = $AppRoot
            RepoUrl = $RepoUrl
            GitRef = $GitRef
            ServerHosts = "localhost,127.0.0.1,$hostname"
            BackendHost = "0.0.0.0"
            BackendPort = "8000"
            FrontendPort = "8080"
            DbName = "techtracker_db"
            DbUser = "techtracker_admin"
            DbPassword = $dbPassword
            DbHost = "localhost"
            DbPort = "5432"
            PgAdminUser = "postgres"
            PgAdminPassword = ""
            AdminUsername = "admin"
            AdminEmail = "admin@example.local"
            AdminPassword = $adminPassword
            LstmUrl = "http://127.0.0.1:8099"
            LstmToken = $lstmToken
            AppUpdateEnabled = "0"
            AppVersion = $appVersion
        }
    }

    $serverHosts = Read-TechTrackerString -Prompt "DJANGO_ALLOWED_HOSTS, через запятую" -Default "localhost,127.0.0.1,$hostname" -Required
    $backendHost = Read-TechTrackerString -Prompt "Backend host" -Default "0.0.0.0" -Required
    $backendPort = Read-TechTrackerString -Prompt "Backend port" -Default "8000" -Required
    $frontendPort = Read-TechTrackerString -Prompt "Frontend port" -Default "8080" -Required

    $dbName = Read-TechTrackerString -Prompt "PostgreSQL DB name" -Default "techtracker_db" -Required
    $dbUser = Read-TechTrackerString -Prompt "PostgreSQL app user" -Default "techtracker_admin" -Required
    $dbPassword = Read-TechTrackerSecret -Prompt "PostgreSQL app user password" -Required
    $dbHost = Read-TechTrackerString -Prompt "PostgreSQL host" -Default "localhost" -Required
    $dbPort = Read-TechTrackerString -Prompt "PostgreSQL port" -Default "5432" -Required
    $pgAdminUser = Read-TechTrackerString -Prompt "PostgreSQL admin user для создания БД" -Default "postgres" -Required
    $pgAdminPassword = Read-TechTrackerSecret -Prompt "PostgreSQL admin password"

    $adminUsername = Read-TechTrackerString -Prompt "TechTracker admin username" -Default "admin" -Required
    $adminEmail = Read-TechTrackerString -Prompt "TechTracker admin email" -Default "admin@example.local" -Required
    $adminPassword = Read-TechTrackerSecret -Prompt "TechTracker admin password" -Required

    $lstmUrl = Read-TechTrackerString -Prompt "Remote LSTM API URL" -Default "http://127.0.0.1:8099"
    $lstmMode = Read-TechTrackerString -Prompt "LSTM token: введите token или оставьте пустым для генерации" -Default ""
    $lstmToken = if ([string]::IsNullOrWhiteSpace($lstmMode)) { New-TechTrackerSecret 32 } else { $lstmMode }
    if ([string]::IsNullOrWhiteSpace($lstmMode)) {
        Write-TechTrackerLog "Сгенерирован LSTM token. Его нужно вставить на LSTM-ПК в LSTM_API_TOKEN." "WARN"
        Write-Host ""
        Write-Host "LSTM_API_TOKEN=$lstmToken" -ForegroundColor Yellow
        Write-Host ""
    }

    $updatesAnswer = Read-TechTrackerString -Prompt "Включить обновления из UI после установки? yes/no" -Default "no"
    $appUpdateEnabled = if ($updatesAnswer.Trim().ToLower() -in @("y", "yes", "1", "true", "да")) { "1" } else { "0" }

    return @{
        AppRoot = $AppRoot
        RepoUrl = $RepoUrl
        GitRef = $GitRef
        ServerHosts = $serverHosts
        BackendHost = $backendHost
        BackendPort = $backendPort
        FrontendPort = $frontendPort
        DbName = $dbName
        DbUser = $dbUser
        DbPassword = $dbPassword
        DbHost = $dbHost
        DbPort = $dbPort
        PgAdminUser = $pgAdminUser
        PgAdminPassword = $pgAdminPassword
        AdminUsername = $adminUsername
        AdminEmail = $adminEmail
        AdminPassword = $adminPassword
        LstmUrl = $lstmUrl
        LstmToken = $lstmToken
        AppUpdateEnabled = $appUpdateEnabled
        AppVersion = $appVersion
    }
}

function Write-TechTrackerInstallEnv {
    param(
        [hashtable]$Config
    )
    $appRoot = $Config.AppRoot
    $envPath = Join-Path $appRoot ".env.local"
    $values = @{
        DJANGO_SECRET_KEY = New-TechTrackerSecret 48
        DJANGO_DEBUG = "False"
        DJANGO_ALLOWED_HOSTS = $Config.ServerHosts
        DB_NAME = $Config.DbName
        DB_USER = $Config.DbUser
        DB_PASSWORD = $Config.DbPassword
        DB_HOST = $Config.DbHost
        DB_PORT = $Config.DbPort
        LSTM_REMOTE_API_BASE_URL = $Config.LstmUrl
        LSTM_REMOTE_API_TOKEN = $Config.LstmToken
        LSTM_REMOTE_TIMEOUT_SEC = "60"
        LSTM_REMOTE_VERIFY_SSL = "0"
        APP_VERSION = $Config.AppVersion
        APP_RELEASE_CHANNEL = "single"
        APP_RELEASE_MANIFEST_URL = (Join-Path $appRoot "deployment\windows\release_manifest.json")
        APP_UPDATE_ENABLED = $Config.AppUpdateEnabled
        APP_UPDATE_SCRIPT = (Join-Path $appRoot "deployment\windows\update_techtracker.ps1")
        APP_UPDATE_WORKDIR = $appRoot
        APP_UPDATE_TIMEOUT_SEC = "3600"
        TECHTRACKER_BACKEND_SERVICE = "TechTrackerBackend"
        TECHTRACKER_FRONTEND_SERVICE = "TechTrackerFrontend"
        TECHTRACKER_LSTM_WORKER_SERVICE = "TechTrackerLSTMWorker"
        TECHTRACKER_BACKEND_HOST = $Config.BackendHost
        TECHTRACKER_BACKEND_PORT = $Config.BackendPort
        TECHTRACKER_FRONTEND_PORT = $Config.FrontendPort
        TECHTRACKER_BACKEND_URL = "http://127.0.0.1:$($Config.BackendPort)"
        TECHTRACKER_LSTM_WORKER_LIMIT = "20"
        TECHTRACKER_LSTM_WORKER_POLL_INTERVAL_SEC = "10"
        TECHTRACKER_LSTM_WORKER_IDLE_SLEEP_SEC = "15"
    }
    Write-TechTrackerEnvFile -Path $envPath -Values $values
    Write-TechTrackerLog ".env.local создан: $envPath" "OK"
}
