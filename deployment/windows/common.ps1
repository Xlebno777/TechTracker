function Get-TechTrackerRoot {
    param([string]$AppRoot)
    if ([string]::IsNullOrWhiteSpace($AppRoot)) {
        $AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
    }
    return (Resolve-Path $AppRoot).Path
}

function Import-TechTrackerEnv {
    param([string]$AppRoot)
    $envFile = Join-Path $AppRoot ".env.local"
    if (-not (Test-Path $envFile)) {
        throw "Missing .env.local: $envFile"
    }
    foreach ($line in Get-Content $envFile) {
        if ($line -match '^\s*#') { continue }
        if ($line -match '^\s*$') { continue }
        if ($line -match '^\s*export\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$' -or $line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim()
            if (($value.StartsWith("'") -and $value.EndsWith("'")) -or ($value.StartsWith('"') -and $value.EndsWith('"'))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [System.Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

function Get-TechTrackerPython {
    param([string]$AppRoot)
    $venvPython = Join-Path $AppRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        return $venvPython
    }
    return "python"
}

function Ensure-TechTrackerLogs {
    param([string]$AppRoot)
    New-Item -ItemType Directory -Force -Path (Join-Path $AppRoot "logs") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $AppRoot "logs\winsw") | Out-Null
}
