$script:TechTrackerInstallLog = $null

function Initialize-TechTrackerInstallLog {
    param([string]$AppRoot)
    $logDir = Join-Path $AppRoot "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $script:TechTrackerInstallLog = Join-Path $logDir "install_$stamp.log"
    "TechTracker installer log: $script:TechTrackerInstallLog" | Out-File -FilePath $script:TechTrackerInstallLog -Encoding UTF8
}

function Write-TechTrackerLog {
    param(
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR", "OK")]
        [string]$Level = "INFO"
    )
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Level, $Message
    if ($Level -eq "ERROR") {
        Write-Host $line -ForegroundColor Red
    } elseif ($Level -eq "WARN") {
        Write-Host $line -ForegroundColor Yellow
    } elseif ($Level -eq "OK") {
        Write-Host $line -ForegroundColor Green
    } else {
        Write-Host $line
    }
    if ($script:TechTrackerInstallLog) {
        Add-Content -Path $script:TechTrackerInstallLog -Value $line -Encoding UTF8
    }
}

function Assert-TechTrackerAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if (-not $isAdmin) {
        throw "Запустите PowerShell от имени администратора."
    }
}

function Invoke-TechTrackerStep {
    param(
        [string]$Name,
        [scriptblock]$Block
    )
    Write-TechTrackerLog "START: $Name"
    try {
        & $Block
        Write-TechTrackerLog "OK: $Name" "OK"
    } catch {
        Write-TechTrackerLog "FAILED: $Name :: $($_.Exception.Message)" "ERROR"
        throw
    }
}

function Test-TechTrackerCommand {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Update-TechTrackerProcessPath {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Read-TechTrackerString {
    param(
        [string]$Prompt,
        [string]$Default = "",
        [switch]$Required
    )
    while ($true) {
        $label = if ($Default) { "$Prompt [$Default]" } else { $Prompt }
        $value = Read-Host $label
        if ([string]::IsNullOrWhiteSpace($value)) {
            $value = $Default
        }
        $value = [string]$value
        if (-not $Required -or -not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
        Write-TechTrackerLog "Поле обязательно: $Prompt" "WARN"
    }
}

function Read-TechTrackerSecret {
    param(
        [string]$Prompt,
        [switch]$Required
    )
    while ($true) {
        $secure = Read-Host $Prompt -AsSecureString
        $value = ConvertFrom-TechTrackerSecureString -SecureString $secure
        if (-not $Required -or -not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
        Write-TechTrackerLog "Секретное поле обязательно: $Prompt" "WARN"
    }
}

function ConvertFrom-TechTrackerSecureString {
    param([Security.SecureString]$SecureString)
    if (-not $SecureString) {
        return ""
    }
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureString)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    } finally {
        if ($ptr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }
}

function New-TechTrackerSecret {
    param([int]$Bytes = 32)
    $data = New-Object byte[] $Bytes
    [Security.Cryptography.RandomNumberGenerator]::Fill($data)
    return [Convert]::ToBase64String($data).TrimEnd("=")
}

function ConvertTo-TechTrackerEnvValue {
    param([string]$Value)
    $text = [string]$Value
    if ($text -match '[\s#"]') {
        $escaped = $text.Replace('\', '\\').Replace('"', '\"')
        return "`"$escaped`""
    }
    return $text
}

function Write-TechTrackerEnvFile {
    param(
        [string]$Path,
        [hashtable]$Values
    )
    if (Test-Path $Path) {
        $backup = "$Path.before_install_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        Copy-Item $Path $backup -Force
        Write-TechTrackerLog "Существующий .env.local сохранен: $backup" "WARN"
    }
    $lines = New-Object System.Collections.Generic.List[string]
    foreach ($key in ($Values.Keys | Sort-Object)) {
        $lines.Add("$key=$(ConvertTo-TechTrackerEnvValue ([string]$Values[$key]))")
    }
    Set-Content -Path $Path -Value $lines -Encoding UTF8
}

function Copy-TechTrackerPackage {
    param(
        [string]$SourceRoot,
        [string]$AppRoot
    )
    $source = (Resolve-Path $SourceRoot).Path.TrimEnd('\')
    $target = $AppRoot.TrimEnd('\')
    if ($source -ieq $target) {
        return
    }
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    if (Test-TechTrackerCommand "robocopy") {
        $args = @(
            $source,
            $target,
            "/E",
            "/XD", ".git", ".venv", "node_modules", "__pycache__", ".idea", ".vscode", "logs", "backups", "dist",
            "/XF", ".env.local", ".env", "*.pyc", "*.pyo", "*.log"
        )
        & robocopy @args | Out-Null
        if ($LASTEXITCODE -gt 7) {
            throw "robocopy завершился с кодом $LASTEXITCODE"
        }
    } else {
        Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force
    }
}

function Assert-TechTrackerSafeIdentifier {
    param(
        [string]$Value,
        [string]$Name
    )
    if ($Value -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "$Name должен содержать только латиницу, цифры и _, и не должен начинаться с цифры."
    }
}

function Find-TechTrackerPsql {
    if (Test-TechTrackerCommand "psql") {
        return "psql"
    }
    $roots = @("C:\Program Files\PostgreSQL", "C:\Program Files (x86)\PostgreSQL")
    foreach ($root in $roots) {
        if (-not (Test-Path $root)) { continue }
        $candidate = Get-ChildItem -Path $root -Filter "psql.exe" -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }
    return ""
}
