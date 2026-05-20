function Test-TechTrackerHttp {
    param(
        [string]$Url,
        [string]$Name,
        [hashtable]$Headers = @{}
    )
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15 -Headers $Headers
        Write-TechTrackerLog "$Name отвечает: HTTP $($response.StatusCode)" "OK"
        return $true
    } catch {
        Write-TechTrackerLog "$Name не отвечает: $Url :: $($_.Exception.Message)" "WARN"
        return $false
    }
}

function Test-TechTrackerInstallation {
    param([hashtable]$Config)
    $backendUrl = "http://127.0.0.1:$($Config.BackendPort)/api/"
    $frontendUrl = "http://127.0.0.1:$($Config.FrontendPort)/"

    Start-Sleep -Seconds 5

    Test-TechTrackerHttp -Url $backendUrl -Name "Backend" | Out-Null
    Test-TechTrackerHttp -Url $frontendUrl -Name "Frontend" | Out-Null

    if (-not [string]::IsNullOrWhiteSpace($Config.LstmUrl)) {
        $healthUrl = $Config.LstmUrl.TrimEnd("/") + "/health"
        $headers = @{}
        if (-not [string]::IsNullOrWhiteSpace($Config.LstmToken)) {
            $headers["X-API-Key"] = $Config.LstmToken
        }
        Test-TechTrackerHttp -Url $healthUrl -Name "Remote LSTM" -Headers $headers | Out-Null
    }
}
