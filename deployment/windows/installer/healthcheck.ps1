function Test-TechTrackerHttp {
    param(
        [string]$Url,
        [string]$Name,
        [hashtable]$Headers = @{},
        [int]$Attempts = 1,
        [int]$DelaySec = 3
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15 -Headers $Headers
            Write-TechTrackerLog "$Name отвечает: HTTP $($response.StatusCode)" "OK"
            return $true
        } catch {
            if ($attempt -lt $Attempts) {
                Write-TechTrackerLog "$Name пока не отвечает, попытка $attempt/$Attempts: $Url :: $($_.Exception.Message)" "WARN"
                Start-Sleep -Seconds $DelaySec
            } else {
                Write-TechTrackerLog "$Name не отвечает: $Url :: $($_.Exception.Message)" "WARN"
                return $false
            }
        }
    }
}

function Test-TechTrackerInstallation {
    param([hashtable]$Config)
    $backendUrl = "http://127.0.0.1:$($Config.BackendPort)/api/"
    $frontendUrl = "http://127.0.0.1:$($Config.FrontendPort)/"

    Start-Sleep -Seconds 5

    Test-TechTrackerHttp -Url $backendUrl -Name "Backend" -Attempts 10 -DelaySec 5 | Out-Null
    Test-TechTrackerHttp -Url $frontendUrl -Name "Frontend" -Attempts 3 -DelaySec 3 | Out-Null

    if ($Config.LstmConfigured -eq "1" -and -not [string]::IsNullOrWhiteSpace($Config.LstmUrl)) {
        $healthUrl = $Config.LstmUrl.TrimEnd("/") + "/health"
        $headers = @{}
        if (-not [string]::IsNullOrWhiteSpace($Config.LstmToken)) {
            $headers["X-API-Key"] = $Config.LstmToken
        }
        Test-TechTrackerHttp -Url $healthUrl -Name "Remote LSTM" -Headers $headers | Out-Null
    } else {
        Write-TechTrackerLog "Remote LSTM healthcheck skipped. Configure LSTM later in Settings -> Integrations." "WARN"
    }
}
