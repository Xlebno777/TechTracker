param(
    [string]$AppRoot = "C:\TechTracker",
    [string]$RepoUrl = "https://github.com/Xlebno777/TechTracker.git",
    [string]$GitRef = "main",
    [switch]$SkipPrerequisites,
    [switch]$SkipPostgreSQLInstall,
    [switch]$SkipDatabase,
    [switch]$SkipFrontendBuild,
    [switch]$SkipServices,
    [switch]$SkipHealthcheck,
    [switch]$AssumeDefaults
)

$ErrorActionPreference = "Stop"

$InstallerRoot = $PSScriptRoot
$PackageRoot = (Resolve-Path (Join-Path $InstallerRoot "..\..\..")).Path

. (Join-Path $InstallerRoot "lib\common.ps1")
. (Join-Path $InstallerRoot "install_prerequisites.ps1")
. (Join-Path $InstallerRoot "configure_env.ps1")
. (Join-Path $InstallerRoot "configure_database.ps1")
. (Join-Path $InstallerRoot "install_project.ps1")
. (Join-Path $InstallerRoot "healthcheck.ps1")

Assert-TechTrackerAdministrator

New-Item -ItemType Directory -Force -Path $AppRoot | Out-Null
Initialize-TechTrackerInstallLog -AppRoot $AppRoot

Write-TechTrackerLog "TechTracker bootstrap started"
Write-TechTrackerLog "PackageRoot: $PackageRoot"
Write-TechTrackerLog "AppRoot: $AppRoot"
Write-TechTrackerLog "RepoUrl: $RepoUrl"
Write-TechTrackerLog "GitRef: $GitRef"

if (-not $SkipPrerequisites) {
    Install-TechTrackerPrerequisites -SkipPostgreSQL:$SkipPostgreSQLInstall
} else {
    Write-TechTrackerLog "Установка зависимостей пропущена параметром SkipPrerequisites" "WARN"
}

Invoke-TechTrackerStep "Подготовка исходников проекта" {
    Initialize-TechTrackerProjectSource -PackageRoot $PackageRoot -AppRoot $AppRoot -RepoUrl $RepoUrl -GitRef $GitRef
}

$config = Read-TechTrackerInstallConfig -AppRoot $AppRoot -RepoUrl $RepoUrl -GitRef $GitRef -AssumeDefaults:$AssumeDefaults

Invoke-TechTrackerStep "Генерация .env.local" {
    Write-TechTrackerInstallEnv -Config $config
}

if (-not $SkipDatabase) {
    Initialize-TechTrackerDatabase -Config $config
} else {
    Write-TechTrackerLog "Настройка PostgreSQL БД пропущена параметром SkipDatabase" "WARN"
}

Install-TechTrackerProject -Config $config -SkipFrontendBuild:$SkipFrontendBuild

if (-not $SkipServices) {
    Invoke-TechTrackerStep "Установка и запуск WinSW сервисов" {
        & (Join-Path $AppRoot "deployment\windows\winsw_services.ps1") -Action Install -AppRoot $AppRoot -StartAfterInstall
        if ($LASTEXITCODE -ne 0) {
            throw "winsw_services.ps1 failed"
        }
    }
} else {
    Write-TechTrackerLog "Установка WinSW сервисов пропущена параметром SkipServices" "WARN"
}

if (-not $SkipHealthcheck) {
    Invoke-TechTrackerStep "Healthcheck установки" {
        Test-TechTrackerInstallation -Config $config
    }
}

Write-TechTrackerLog "TechTracker установлен." "OK"
Write-Host ""
Write-Host "Готово." -ForegroundColor Green
Write-Host "UI: http://localhost:$($config.FrontendPort)"
Write-Host "Путь установки: $AppRoot"
Write-Host "Лог установки: $script:TechTrackerInstallLog"
Write-Host ""
if ($config.AppUpdateEnabled -ne "1") {
    Write-Host "Обновления из UI выключены. Для включения установите APP_UPDATE_ENABLED=1 в .env.local после ручной проверки update_techtracker.ps1." -ForegroundColor Yellow
}
