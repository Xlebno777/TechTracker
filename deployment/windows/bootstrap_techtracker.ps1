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
$installer = Join-Path $PSScriptRoot "installer\bootstrap_techtracker.ps1"
& $installer @PSBoundParameters
