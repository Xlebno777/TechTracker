function Read-TechTrackerInstallConfig {
    param(
        [string]$AppRoot,
        [string]$RepoUrl,
        [string]$GitRef,
        [switch]$AssumeDefaults
    )
    $hostname = "localhost"
    try {
        $hostname = [System.Net.Dns]::GetHostName()
    } catch {
        $hostname = "localhost"
    }
    $versionPath = Join-Path $AppRoot "VERSION"
    $appVersion = if (Test-Path $versionPath) { (Get-Content $versionPath -Raw).Trim() } else { "0.1.0" }

    if ($AssumeDefaults) {
        $dbPassword = New-TechTrackerSecret 24
        $pgAdminPassword = New-TechTrackerSecret 24
        $adminPassword = New-TechTrackerSecret 18
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
            PgAdminPassword = $pgAdminPassword
            AdminUsername = "admin"
            AdminEmail = "admin@example.local"
            AdminPassword = $adminPassword
            LstmUrl = "http://127.0.0.1:8099"
            LstmToken = ""
            LstmConfigured = "0"
            AppUpdateEnabled = "0"
            AppVersion = $appVersion
        }
    }

    Write-Host ""
    Write-Host "Этап 1. Сетевые параметры приложения." -ForegroundColor Cyan
    Write-Host "Здесь задаются адреса и порты, по которым браузер и backend будут открывать TechTracker; обычно достаточно оставить значения по умолчанию." -ForegroundColor DarkGray
    $serverHosts = Read-TechTrackerString -Prompt "DJANGO_ALLOWED_HOSTS, через запятую" -Default "localhost,127.0.0.1,$hostname" -Required
    $backendHost = Read-TechTrackerString -Prompt "Backend host" -Default "0.0.0.0" -Required
    $backendPort = Read-TechTrackerString -Prompt "Backend port" -Default "8000" -Required
    $frontendPort = Read-TechTrackerString -Prompt "Frontend port" -Default "8080" -Required

    Write-Host ""
    Write-Host "Этап 2. База данных приложения." -ForegroundColor Cyan
    Write-Host "Эти параметры создают отдельную базу и отдельного пользователя для TechTracker; это не пользователь для входа в web-интерфейс." -ForegroundColor DarkGray
    $dbName = Read-TechTrackerString -Prompt "PostgreSQL DB name" -Default "techtracker_db" -Required
    $dbUser = Read-TechTrackerString -Prompt "PostgreSQL app user" -Default "techtracker_admin" -Required
    $dbPassword = Read-TechTrackerSecret -Prompt "PostgreSQL app user password" -Required
    $dbHost = Read-TechTrackerString -Prompt "PostgreSQL host" -Default "localhost" -Required
    $dbPort = Read-TechTrackerString -Prompt "PostgreSQL port" -Default "5432" -Required

    Write-Host ""
    Write-Host "Этап 3. Администратор PostgreSQL." -ForegroundColor Cyan
    Write-Host "Эта учетная запись нужна установщику один раз, чтобы создать базу и выдать права; обычно это пользователь postgres." -ForegroundColor DarkGray
    $pgAdminUser = Read-TechTrackerString -Prompt "PostgreSQL admin user для создания БД" -Default "postgres" -Required
    $pgAdminPassword = Read-TechTrackerSecret -Prompt "PostgreSQL admin password"

    Write-Host ""
    Write-Host "Этап 4. Администратор web-интерфейса TechTracker." -ForegroundColor Cyan
    Write-Host "Эти логин, email и пароль будут использоваться для первого входа в интерфейс системы после установки." -ForegroundColor DarkGray
    $adminUsername = Read-TechTrackerString -Prompt "TechTracker admin username" -Default "admin" -Required
    $adminEmail = Read-TechTrackerString -Prompt "TechTracker admin email" -Default "admin@example.local" -Required
    $adminPassword = Read-TechTrackerSecret -Prompt "TechTracker admin password" -Required

    Write-Host ""
    Write-Host "Этап 5. Обновления приложения." -ForegroundColor Cyan
    Write-Host "Эта настройка разрешает запуск обновлений из web-интерфейса; безопаснее включать её после первой ручной проверки установки." -ForegroundColor DarkGray
    $updatesAnswer = Read-TechTrackerString -Prompt "Включить обновления из UI после установки? yes/no" -Default "no"
    $appUpdateEnabled = if ($updatesAnswer.Trim().ToLower() -in @("y", "yes", "1", "true", "да")) { "1" } else { "0" }
    $lstmUrl = "http://127.0.0.1:8099"
    $lstmToken = ""

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
        LstmConfigured = "0"
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
        TECHTRACKER_ADMIN_USERNAME = $Config.AdminUsername
        TECHTRACKER_ADMIN_EMAIL = $Config.AdminEmail
        LSTM_REMOTE_API_BASE_URL = $Config.LstmUrl
        LSTM_REMOTE_API_TOKEN = $Config.LstmToken
        LSTM_REMOTE_CONFIGURED = $Config.LstmConfigured
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
