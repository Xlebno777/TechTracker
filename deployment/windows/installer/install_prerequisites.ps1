function Install-TechTrackerChocolatey {
    if (Test-TechTrackerCommand "choco") {
        Write-TechTrackerLog "Chocolatey already installed" "OK"
        return
    }

    Write-TechTrackerLog "winget not found. Installing Chocolatey as automatic fallback." "WARN"
    Set-ExecutionPolicy Bypass -Scope Process -Force
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
    $installScript = (New-Object System.Net.WebClient).DownloadString("https://community.chocolatey.org/install.ps1")
    Invoke-Expression $installScript
    Update-TechTrackerProcessPath

    if (-not (Test-TechTrackerCommand "choco")) {
        throw "Chocolatey installation failed: choco command not found."
    }
    Write-TechTrackerLog "Chocolatey installed" "OK"
}

function Install-TechTrackerChocolateyPackage {
    param(
        [string]$Package,
        [string]$Name,
        [string]$PackageParameters = "",
        [string]$InstallArguments = ""
    )

    Install-TechTrackerChocolatey
    Write-TechTrackerLog "Installing $Name via Chocolatey ($Package)"

    $args = @("install", $Package, "-y", "--no-progress")
    if (-not [string]::IsNullOrWhiteSpace($PackageParameters)) {
        $args += "--params"
        $args += $PackageParameters
    }
    if (-not [string]::IsNullOrWhiteSpace($InstallArguments)) {
        $args += "--ia"
        $args += $InstallArguments
    }

    & choco @args
    if ($LASTEXITCODE -ne 0) {
        throw "Chocolatey could not install $Name ($Package). Exit code: $LASTEXITCODE"
    }
    Update-TechTrackerProcessPath
}

function Start-TechTrackerPostgreSQLService {
    $services = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "postgresql*" -or $_.DisplayName -like "postgresql*" }
    foreach ($service in $services) {
        if ($service.Status -ne "Running") {
            Write-TechTrackerLog "Starting PostgreSQL service: $($service.Name)"
            Start-Service -Name $service.Name
            Start-Sleep -Seconds 3
        }
    }
}

function Install-TechTrackerPackage {
    param(
        [string]$WingetId,
        [string]$ChocolateyPackage,
        [string]$Name,
        [string]$ChocolateyPackageParameters = "",
        [string]$ChocolateyInstallArguments = ""
    )

    if (Test-TechTrackerCommand "winget") {
        Write-TechTrackerLog "Checking package: $Name ($WingetId)"
        $list = & winget list --id $WingetId -e --accept-source-agreements 2>$null
        if ($LASTEXITCODE -eq 0 -and ($list -match [regex]::Escape($WingetId))) {
            Write-TechTrackerLog "$Name already installed" "OK"
            return
        }

        Write-TechTrackerLog "Installing $Name via winget"
        & winget install --id $WingetId -e --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            Write-TechTrackerLog "winget could not install $Name. Falling back to Chocolatey." "WARN"
        } else {
            Update-TechTrackerProcessPath
            return
        }
    }

    Install-TechTrackerChocolateyPackage -Package $ChocolateyPackage -Name $Name -PackageParameters $ChocolateyPackageParameters -InstallArguments $ChocolateyInstallArguments
}

function Install-TechTrackerPrerequisites {
    param(
        [switch]$SkipPostgreSQL,
        [string]$PostgreSQLPassword = "",
        [string]$PostgreSQLPort = "5432"
    )

    Invoke-TechTrackerStep "Install Git" {
        if (-not (Test-TechTrackerCommand "git")) {
            Install-TechTrackerPackage -WingetId "Git.Git" -ChocolateyPackage "git" -Name "Git"
        }
        git --version | ForEach-Object { Write-TechTrackerLog $_ }
    }

    Invoke-TechTrackerStep "Install Python 3.12" {
        if (-not (Test-TechTrackerCommand "python")) {
            Install-TechTrackerPackage -WingetId "Python.Python.3.12" -ChocolateyPackage "python312" -Name "Python 3.12"
        }
        python --version | ForEach-Object { Write-TechTrackerLog $_ }
    }

    Invoke-TechTrackerStep "Install Node.js LTS" {
        if (-not (Test-TechTrackerCommand "node")) {
            Install-TechTrackerPackage -WingetId "OpenJS.NodeJS.LTS" -ChocolateyPackage "nodejs-lts" -Name "Node.js LTS"
        }
        node --version | ForEach-Object { Write-TechTrackerLog "node $($_)" }
        npm --version | ForEach-Object { Write-TechTrackerLog "npm $($_)" }
    }

    if ($SkipPostgreSQL) {
        Write-TechTrackerLog "PostgreSQL install skipped" "WARN"
        return
    }

    Invoke-TechTrackerStep "Install PostgreSQL" {
        $psql = Find-TechTrackerPsql
        if (-not $psql) {
            if ([string]::IsNullOrWhiteSpace($PostgreSQLPassword)) {
                throw "PostgreSQL admin password is required for automatic PostgreSQL installation."
            }
            $params = "/Password:$PostgreSQLPassword /Port:$PostgreSQLPort"
            Install-TechTrackerPackage -WingetId "PostgreSQL.PostgreSQL" -ChocolateyPackage "postgresql17" -Name "PostgreSQL" -ChocolateyPackageParameters $params -ChocolateyInstallArguments "--enable-components server,commandlinetools"
            $psql = Find-TechTrackerPsql
        }
        if (-not $psql) {
            throw "psql not found after PostgreSQL installation. Check PostgreSQL and PATH."
        }
        Start-TechTrackerPostgreSQLService
        Write-TechTrackerLog "psql: $psql"
    }
}
