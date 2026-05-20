$script:TechTrackerPythonInstallerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$script:TechTrackerNodeInstallerUrl = "https://nodejs.org/dist/v22.16.0/node-v22.16.0-x64.msi"
$script:TechTrackerPostgreSQLInstallerUrl = "https://get.enterprisedb.com/postgresql/postgresql-17.5-1-windows-x64.exe"

function Initialize-TechTrackerTls {
    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
}

function New-TechTrackerInstallerTempDir {
    $dir = Join-Path $env:TEMP "TechTrackerInstallers"
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    return $dir
}

function Save-TechTrackerDownload {
    param(
        [string]$Url,
        [string]$FileName
    )
    Initialize-TechTrackerTls
    $dir = New-TechTrackerInstallerTempDir
    $path = Join-Path $dir $FileName
    if (Test-Path $path) {
        Write-TechTrackerLog "Using cached installer: $path"
        return $path
    }

    Write-TechTrackerLog "Downloading $Url"
    try {
        Invoke-WebRequest -Uri $Url -OutFile $path -UseBasicParsing
    } catch {
        Write-TechTrackerLog "Invoke-WebRequest failed, retrying with WebClient: $($_.Exception.Message)" "WARN"
        $client = New-Object System.Net.WebClient
        $client.DownloadFile($Url, $path)
    }

    if (-not (Test-Path $path)) {
        throw "Download failed: $Url"
    }
    return $path
}

function Invoke-TechTrackerNativeInstaller {
    param(
        [string]$Path,
        [string]$Arguments,
        [string]$Name
    )
    Write-TechTrackerLog "Running installer for $Name"
    $process = Start-Process -FilePath $Path -ArgumentList $Arguments -Wait -PassThru
    $exitCode = [int]$process.ExitCode
    if ($exitCode -eq 0) {
        Write-TechTrackerLog "$Name installer completed" "OK"
        return
    }
    if ($exitCode -eq 3010 -or $exitCode -eq 1641) {
        Write-TechTrackerLog "$Name installer completed and requested reboot. Continuing; reboot after installation if service does not start." "WARN"
        return
    }
    throw "$Name installer failed. Exit code: $exitCode"
}

function Get-TechTrackerGitInstallerUrl {
    Initialize-TechTrackerTls
    try {
        $release = Invoke-RestMethod -Uri "https://api.github.com/repos/git-for-windows/git/releases/latest" -Headers @{ "User-Agent" = "TechTrackerInstaller" }
        $asset = $release.assets | Where-Object { $_.name -match '^Git-.*-64-bit\.exe$' } | Select-Object -First 1
        if ($asset -and $asset.browser_download_url) {
            return [string]$asset.browser_download_url
        }
    } catch {
        Write-TechTrackerLog "Could not resolve latest Git for Windows release: $($_.Exception.Message)" "WARN"
    }
    return "https://github.com/git-for-windows/git/releases/download/v2.49.0.windows.1/Git-2.49.0-64-bit.exe"
}

function Install-TechTrackerGitDirect {
    $url = Get-TechTrackerGitInstallerUrl
    $installer = Save-TechTrackerDownload -Url $url -FileName "git-for-windows-64-bit.exe"
    Invoke-TechTrackerNativeInstaller -Path $installer -Arguments "/VERYSILENT /NORESTART /NOCANCEL /SP- /CLOSEAPPLICATIONS" -Name "Git"
    Update-TechTrackerProcessPath
}

function Install-TechTrackerPythonDirect {
    $installer = Save-TechTrackerDownload -Url $script:TechTrackerPythonInstallerUrl -FileName "python-3.12.10-amd64.exe"
    Invoke-TechTrackerNativeInstaller -Path $installer -Arguments "/quiet InstallAllUsers=1 PrependPath=1 Include_launcher=1 Include_pip=1 Include_test=0" -Name "Python 3.12"
    Update-TechTrackerProcessPath
}

function Install-TechTrackerNodeDirect {
    $installer = Save-TechTrackerDownload -Url $script:TechTrackerNodeInstallerUrl -FileName "node-v22.16.0-x64.msi"
    Invoke-TechTrackerNativeInstaller -Path "msiexec.exe" -Arguments "/i `"$installer`" /qn /norestart" -Name "Node.js LTS"
    Update-TechTrackerProcessPath
}

function Install-TechTrackerPostgreSQLDirect {
    param(
        [string]$PostgreSQLPassword,
        [string]$PostgreSQLPort = "5432"
    )
    if ([string]::IsNullOrWhiteSpace($PostgreSQLPassword)) {
        throw "PostgreSQL admin password is required for automatic PostgreSQL installation."
    }
    $installer = Save-TechTrackerDownload -Url $script:TechTrackerPostgreSQLInstallerUrl -FileName "postgresql-17.5-1-windows-x64.exe"
    $args = "--mode unattended --unattendedmodeui none --superpassword `"$PostgreSQLPassword`" --serverport $PostgreSQLPort --disable-components stackbuilder"
    Invoke-TechTrackerNativeInstaller -Path $installer -Arguments $args -Name "PostgreSQL 17"
    Update-TechTrackerProcessPath
}

function Start-TechTrackerPostgreSQLService {
    $services = Get-Service -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "postgresql*" -or $_.DisplayName -like "postgresql*" }
    foreach ($service in $services) {
        if ($service.Status -ne "Running") {
            Write-TechTrackerLog "Starting PostgreSQL service: $($service.Name)"
            Start-Service -Name $service.Name
            Start-Sleep -Seconds 5
        }
    }
}

function Install-TechTrackerWingetPackage {
    param(
        [string]$WingetId,
        [string]$Name
    )

    if (-not (Test-TechTrackerCommand "winget")) {
        return $false
    }

    Write-TechTrackerLog "Checking package: $Name ($WingetId)"
    $list = & winget list --id $WingetId -e --accept-source-agreements 2>$null
    if ($LASTEXITCODE -eq 0 -and ($list -match [regex]::Escape($WingetId))) {
        Write-TechTrackerLog "$Name already installed" "OK"
        return $true
    }

    Write-TechTrackerLog "Installing $Name via winget"
    & winget install --id $WingetId -e --accept-source-agreements --accept-package-agreements |
        ForEach-Object { Write-TechTrackerLog $_ }
    if ($LASTEXITCODE -eq 0) {
        Update-TechTrackerProcessPath
        return $true
    }

    Write-TechTrackerLog "winget could not install $Name. Using direct installer fallback." "WARN"
    return $false
}

function Install-TechTrackerPrerequisites {
    param(
        [switch]$SkipPostgreSQL,
        [string]$PostgreSQLPassword = "",
        [string]$PostgreSQLPort = "5432"
    )

    Invoke-TechTrackerStep "Install Git" {
        if (-not (Test-TechTrackerCommand "git")) {
            $installed = Install-TechTrackerWingetPackage -WingetId "Git.Git" -Name "Git"
            if (-not $installed) { Install-TechTrackerGitDirect }
        }
        git --version | ForEach-Object { Write-TechTrackerLog $_ }
    }

    Invoke-TechTrackerStep "Install Python 3.12" {
        if (-not (Test-TechTrackerCommand "python")) {
            $installed = Install-TechTrackerWingetPackage -WingetId "Python.Python.3.12" -Name "Python 3.12"
            if (-not $installed) { Install-TechTrackerPythonDirect }
        }
        python --version | ForEach-Object { Write-TechTrackerLog $_ }
    }

    Invoke-TechTrackerStep "Install Node.js LTS" {
        if (-not (Test-TechTrackerCommand "node")) {
            $installed = Install-TechTrackerWingetPackage -WingetId "OpenJS.NodeJS.LTS" -Name "Node.js LTS"
            if (-not $installed) { Install-TechTrackerNodeDirect }
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
            $installed = Install-TechTrackerWingetPackage -WingetId "PostgreSQL.PostgreSQL" -Name "PostgreSQL"
            if (-not $installed) {
                Install-TechTrackerPostgreSQLDirect -PostgreSQLPassword $PostgreSQLPassword -PostgreSQLPort $PostgreSQLPort
            }
            $psql = Find-TechTrackerPsql
        }
        if (-not $psql) {
            throw "psql not found after PostgreSQL installation. Check PostgreSQL and PATH."
        }
        Start-TechTrackerPostgreSQLService
        Write-TechTrackerLog "psql: $psql"
    }
}
