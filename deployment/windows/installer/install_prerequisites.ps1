function Install-TechTrackerWingetPackage {
    param(
        [string]$Id,
        [string]$Name
    )
    if (-not (Test-TechTrackerCommand "winget")) {
        throw "winget не найден. Установите App Installer или поставьте $Name вручную."
    }
    Write-TechTrackerLog "Проверка пакета: $Name ($Id)"
    $list = & winget list --id $Id -e --accept-source-agreements 2>$null
    if ($LASTEXITCODE -eq 0 -and ($list -match [regex]::Escape($Id))) {
        Write-TechTrackerLog "$Name уже установлен" "OK"
        return
    }
    Write-TechTrackerLog "Установка $Name через winget"
    & winget install --id $Id -e --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget не смог установить $Name ($Id)"
    }
    Update-TechTrackerProcessPath
}

function Install-TechTrackerPrerequisites {
    param(
        [switch]$SkipPostgreSQL
    )
    Invoke-TechTrackerStep "Установка Git" {
        if (-not (Test-TechTrackerCommand "git")) {
            Install-TechTrackerWingetPackage -Id "Git.Git" -Name "Git"
        }
        git --version | ForEach-Object { Write-TechTrackerLog $_ }
    }

    Invoke-TechTrackerStep "Установка Python 3.12" {
        if (-not (Test-TechTrackerCommand "python")) {
            Install-TechTrackerWingetPackage -Id "Python.Python.3.12" -Name "Python 3.12"
        }
        python --version | ForEach-Object { Write-TechTrackerLog $_ }
    }

    Invoke-TechTrackerStep "Установка Node.js LTS" {
        if (-not (Test-TechTrackerCommand "node")) {
            Install-TechTrackerWingetPackage -Id "OpenJS.NodeJS.LTS" -Name "Node.js LTS"
        }
        node --version | ForEach-Object { Write-TechTrackerLog "node $($_)" }
        npm --version | ForEach-Object { Write-TechTrackerLog "npm $($_)" }
    }

    if (-not $SkipPostgreSQL) {
        Invoke-TechTrackerStep "Проверка PostgreSQL" {
            $psql = Find-TechTrackerPsql
            if (-not $psql) {
                Install-TechTrackerWingetPackage -Id "PostgreSQL.PostgreSQL" -Name "PostgreSQL"
                $psql = Find-TechTrackerPsql
            }
            if (-not $psql) {
                throw "psql не найден после установки PostgreSQL. Проверьте PostgreSQL и PATH."
            }
            Write-TechTrackerLog "psql: $psql"
        }
    }
}
