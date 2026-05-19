param(
    [ValidateSet("Install", "Reinstall", "Start", "Stop", "Restart", "Uninstall", "Status")]
    [string]$Action = "Install",
    [string]$AppRoot = "C:\TechTracker",
    [string]$WinSWVersion = "3.0.0",
    [string]$WinSWExe = "",
    [switch]$StartAfterInstall
)

$ErrorActionPreference = "Stop"

$AppRoot = (Resolve-Path $AppRoot).Path
$WindowsDir = Join-Path $AppRoot "deployment\windows"
$ServiceDir = Join-Path $WindowsDir "services"
$LogDir = Join-Path $AppRoot "logs\winsw"
$BinDir = Join-Path $WindowsDir "bin"
New-Item -ItemType Directory -Force -Path $ServiceDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

function Write-Step {
    param([string]$Message)
    Write-Host "[WinSW] $Message"
}

function Get-WinSWBinary {
    if (-not [string]::IsNullOrWhiteSpace($WinSWExe)) {
        if (-not (Test-Path $WinSWExe)) {
            throw "WinSWExe not found: $WinSWExe"
        }
        return (Resolve-Path $WinSWExe).Path
    }

    $local = Join-Path $BinDir "WinSW-x64.exe"
    if (Test-Path $local) {
        return $local
    }

    $url = "https://github.com/winsw/winsw/releases/download/v$WinSWVersion/WinSW-x64.exe"
    Write-Step "Downloading WinSW $WinSWVersion from $url"
    Invoke-WebRequest -Uri $url -OutFile $local
    return $local
}

function XmlEscape {
    param([string]$Value)
    return [System.Security.SecurityElement]::Escape($Value)
}

function New-ServiceXml {
    param(
        [string]$Id,
        [string]$Name,
        [string]$Description,
        [string]$Script
    )
    $scriptPath = Join-Path $WindowsDir $Script
    $escapedArgs = XmlEscape "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -AppRoot `"$AppRoot`""
    $escapedWorkdir = XmlEscape $AppRoot
    $escapedLogDir = XmlEscape $LogDir
    $escapedName = XmlEscape $Name
    $escapedDescription = XmlEscape $Description
    return @"
<service>
  <id>$Id</id>
  <name>$escapedName</name>
  <description>$escapedDescription</description>
  <executable>powershell.exe</executable>
  <arguments>$escapedArgs</arguments>
  <workingdirectory>$escapedWorkdir</workingdirectory>
  <logpath>$escapedLogDir</logpath>
  <log mode="roll-by-size-time">
    <sizeThreshold>10485760</sizeThreshold>
    <pattern>yyyyMMdd</pattern>
    <autoRollAtTime>00:00:00</autoRollAtTime>
    <zipOlderThanNumDays>14</zipOlderThanNumDays>
  </log>
  <onfailure action="restart" delay="10 sec" />
  <onfailure action="restart" delay="30 sec" />
  <resetfailure>1 hour</resetfailure>
  <stopparentprocessfirst>true</stopparentprocessfirst>
</service>
"@
}

$Services = @(
    @{
        Id = "TechTrackerBackend"
        Name = "TechTracker Backend"
        Description = "Django API server for TechTracker"
        Script = "service_backend.ps1"
    },
    @{
        Id = "TechTrackerFrontend"
        Name = "TechTracker Frontend"
        Description = "Vue static frontend and API proxy for TechTracker"
        Script = "service_frontend.ps1"
    },
    @{
        Id = "TechTrackerLSTMWorker"
        Name = "TechTracker LSTM Worker"
        Description = "Background worker polling remote LSTM forecast jobs"
        Script = "service_lstm_worker.ps1"
    }
)

function Invoke-WinSW {
    param(
        [hashtable]$Service,
        [string]$Command
    )
    $exe = Join-Path $ServiceDir "$($Service.Id).exe"
    if (-not (Test-Path $exe)) {
        throw "Service executable not found: $exe. Run Install first."
    }
    Write-Step "$($Service.Id): $Command"
    & $exe $Command
}

function Install-One {
    param([hashtable]$Service, [bool]$Force)
    $winsw = Get-WinSWBinary
    $serviceExe = Join-Path $ServiceDir "$($Service.Id).exe"
    $serviceXml = Join-Path $ServiceDir "$($Service.Id).xml"

    Copy-Item $winsw $serviceExe -Force
    New-ServiceXml -Id $Service.Id -Name $Service.Name -Description $Service.Description -Script $Service.Script |
        Set-Content -Path $serviceXml -Encoding UTF8

    $exists = Get-Service -Name $Service.Id -ErrorAction SilentlyContinue
    if ($exists -and $Force) {
        try { Invoke-WinSW -Service $Service -Command "stop" } catch {}
        Invoke-WinSW -Service $Service -Command "uninstall"
        $exists = $null
    }
    if (-not $exists) {
        Invoke-WinSW -Service $Service -Command "install"
    } else {
        Write-Step "$($Service.Id): already installed, XML refreshed"
    }
}

switch ($Action) {
    "Install" {
        foreach ($svc in $Services) { Install-One -Service $svc -Force:$false }
        if ($StartAfterInstall) {
            foreach ($svc in $Services) { Invoke-WinSW -Service $svc -Command "start" }
        }
    }
    "Reinstall" {
        foreach ($svc in $Services) { Install-One -Service $svc -Force:$true }
        if ($StartAfterInstall) {
            foreach ($svc in $Services) { Invoke-WinSW -Service $svc -Command "start" }
        }
    }
    "Start" {
        foreach ($svc in $Services) { Invoke-WinSW -Service $svc -Command "start" }
    }
    "Stop" {
        foreach ($svc in @($Services[2], $Services[1], $Services[0])) { try { Invoke-WinSW -Service $svc -Command "stop" } catch {} }
    }
    "Restart" {
        foreach ($svc in @($Services[2], $Services[1], $Services[0])) { try { Invoke-WinSW -Service $svc -Command "stop" } catch {} }
        foreach ($svc in $Services) { Invoke-WinSW -Service $svc -Command "start" }
    }
    "Uninstall" {
        foreach ($svc in @($Services[2], $Services[1], $Services[0])) {
            try { Invoke-WinSW -Service $svc -Command "stop" } catch {}
            Invoke-WinSW -Service $svc -Command "uninstall"
        }
    }
    "Status" {
        foreach ($svc in $Services) { Invoke-WinSW -Service $svc -Command "status" }
    }
}
