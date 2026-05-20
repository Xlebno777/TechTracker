function Initialize-TechTrackerProjectSource {
    param(
        [string]$PackageRoot,
        [string]$AppRoot,
        [string]$RepoUrl,
        [string]$GitRef
    )
    $managePy = Join-Path $AppRoot "manage.py"
    if (Test-Path $managePy) {
        Write-TechTrackerLog "Проект уже найден: $AppRoot"
        Set-Location $AppRoot
        if (Test-TechTrackerCommand "git") {
            try {
                git fetch --all --tags --prune
                if ($GitRef) {
                    git checkout $GitRef
                }
            } catch {
                Write-TechTrackerLog "Не удалось обновить git checkout: $($_.Exception.Message)" "WARN"
            }
        }
        return
    }

    $packageManagePy = Join-Path $PackageRoot "manage.py"
    if (Test-Path $packageManagePy) {
        Write-TechTrackerLog "Копирование release package в $AppRoot"
        Copy-TechTrackerPackage -SourceRoot $PackageRoot -AppRoot $AppRoot
        return
    }

    if (-not (Test-TechTrackerCommand "git")) {
        throw "git не найден, невозможно скачать проект из репозитория."
    }

    Write-TechTrackerLog "Клонирование проекта: $RepoUrl -> $AppRoot"
    git clone $RepoUrl $AppRoot
    if ($LASTEXITCODE -ne 0) {
        throw "git clone завершился с кодом $LASTEXITCODE"
    }
    Set-Location $AppRoot
    if ($GitRef) {
        git checkout $GitRef
        if ($LASTEXITCODE -ne 0) {
            throw "git checkout $GitRef завершился с кодом $LASTEXITCODE"
        }
    }
}

function Install-TechTrackerProject {
    param(
        [hashtable]$Config,
        [switch]$SkipFrontendBuild
    )
    $appRoot = $Config.AppRoot
    Set-Location $appRoot

    Invoke-TechTrackerStep "Создание Python virtualenv" {
        if (-not (Test-Path ".venv\Scripts\python.exe")) {
            python -m venv .venv
            if ($LASTEXITCODE -ne 0) {
                throw "python -m venv завершился с кодом $LASTEXITCODE"
            }
        }
    }

    $python = Join-Path $appRoot ".venv\Scripts\python.exe"

    Invoke-TechTrackerStep "Установка backend зависимостей" {
        & $python -m pip install --upgrade pip
        if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
        & $python -m pip install -r requirements.txt
        if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
    }

    Invoke-TechTrackerStep "Django migrations" {
        & $python manage.py migrate --noinput
        if ($LASTEXITCODE -ne 0) { throw "manage.py migrate failed" }
    }

    Invoke-TechTrackerStep "Django collectstatic" {
        & $python manage.py collectstatic --noinput
        if ($LASTEXITCODE -ne 0) { throw "manage.py collectstatic failed" }
    }

    Invoke-TechTrackerStep "Создание администратора TechTracker" {
        $oldPassword = $env:TECHTRACKER_ADMIN_PASSWORD
        try {
            $env:TECHTRACKER_ADMIN_PASSWORD = $Config.AdminPassword
            & $python manage.py ensure_admin_user --username $Config.AdminUsername --email $Config.AdminEmail --password-env TECHTRACKER_ADMIN_PASSWORD
            if ($LASTEXITCODE -ne 0) { throw "ensure_admin_user failed" }
        } finally {
            $env:TECHTRACKER_ADMIN_PASSWORD = $oldPassword
        }
    }

    if (-not $SkipFrontendBuild) {
        Invoke-TechTrackerStep "Frontend npm ci + build" {
            Push-Location (Join-Path $appRoot "techtracker_vue")
            try {
                npm ci
                if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
                npm run build
                if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
            } finally {
                Pop-Location
            }
        }
    }
}
