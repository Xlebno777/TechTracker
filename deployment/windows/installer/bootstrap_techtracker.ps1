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

if ($SkipPrerequisites)
{
    Write-TechTrackerLog "Prerequisites step skipped by SkipPrerequisites" "WARN"
}

if (-not $SkipPrerequisites)
{
    Install-TechTrackerPrerequisites -SkipPostgreSQL
}

Write-TechTrackerLog "START: project source preparation"
Initialize-TechTrackerProjectSource -PackageRoot $PackageRoot -AppRoot $AppRoot -RepoUrl $RepoUrl -GitRef $GitRef
Write-TechTrackerLog "OK: project source preparation" "OK"

$config = Read-TechTrackerInstallConfig -AppRoot $AppRoot -RepoUrl $RepoUrl -GitRef $GitRef -AssumeDefaults:$AssumeDefaults

if (-not $SkipPrerequisites -and -not $SkipPostgreSQLInstall)
{
    if (-not (Find-TechTrackerPsql) -and [string]::IsNullOrWhiteSpace($config.PgAdminPassword))
    {
        $config.PgAdminPassword = Read-TechTrackerSecret -Prompt "PostgreSQL admin password для автоматической установки PostgreSQL" -Required
    }
    Install-TechTrackerPrerequisites -SkipPostgreSQL:$false -PostgreSQLPassword $config.PgAdminPassword -PostgreSQLPort $config.DbPort
}

Write-TechTrackerLog "START: .env.local generation"
Write-TechTrackerInstallEnv -Config $config
Write-TechTrackerLog "OK: .env.local generation" "OK"

if ($SkipDatabase)
{
    Write-TechTrackerLog "Database step skipped by SkipDatabase" "WARN"
}

if (-not $SkipDatabase)
{
    Initialize-TechTrackerDatabase -Config $config
}

Install-TechTrackerProject -Config $config -SkipFrontendBuild:$SkipFrontendBuild

if ($SkipServices)
{
    Write-TechTrackerLog "WinSW services step skipped by SkipServices" "WARN"
}

if (-not $SkipServices)
{
    Write-TechTrackerLog "START: WinSW services install and start"
    & (Join-Path $AppRoot "deployment\windows\winsw_services.ps1") -Action Reinstall -AppRoot $AppRoot -StartAfterInstall
    if ($LASTEXITCODE -ne 0)
    {
        throw "winsw_services.ps1 failed"
    }
    Write-TechTrackerLog "OK: WinSW services install and start" "OK"
}

if (-not $SkipHealthcheck)
{
    Write-TechTrackerLog "START: installation healthcheck"
    Test-TechTrackerInstallation -Config $config
    Write-TechTrackerLog "OK: installation healthcheck" "OK"
}

Write-TechTrackerLog "TechTracker установлен." "OK"
Write-Host ""
Write-Host "Готово." -ForegroundColor Green
Write-Host "UI: http://localhost:$($config.FrontendPort)"
Write-Host "Путь установки: $AppRoot"
Write-Host "Лог установки: $script:TechTrackerInstallLog"
Write-Host ""
if ($config.AppUpdateEnabled -ne "1")
{
    Write-Host "Обновления из UI выключены. Для включения установите APP_UPDATE_ENABLED=1 в .env.local после ручной проверки update_techtracker.ps1." -ForegroundColor Yellow
}
