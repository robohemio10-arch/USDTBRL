$ErrorActionPreference = "Stop"

$ProjectRoot = "E:\USDTBRL"
$ConfigPath = "config/config.yml"
$PythonExe = "E:\USDTBRL\.venv\Scripts\python.exe"
$DotenvPath = Join-Path $ProjectRoot ".env"
$LogPath = "E:\USDTBRL\data\logs\watchdog_health_ntfy.log"
$DotenvImported = @{}

function Write-Log {
    param([string]$Message)

    $logDir = Split-Path $LogPath -Parent
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    }

    Add-Content -Path $LogPath -Value "[$(Get-Date -Format o)] $Message"
}

function Import-DotenvToProcess {
    if (-not (Test-Path $DotenvPath)) {
        return
    }

    foreach ($rawLine in [System.IO.File]::ReadAllLines($DotenvPath, [System.Text.Encoding]::UTF8)) {
        $line = $rawLine.Trim()

        if ([string]::IsNullOrWhiteSpace($line)) {
            continue
        }

        if ($line.StartsWith("#")) {
            continue
        }

        $match = [Regex]::Match($line, '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$')
        if (-not $match.Success) {
            continue
        }

        $key = $match.Groups[1].Value
        $value = $match.Groups[2].Value.Trim()

        if ($value.Length -ge 2) {
            $hasDoubleQuotes = $value.StartsWith('"') -and $value.EndsWith('"')
            $hasSingleQuotes = $value.StartsWith("'") -and $value.EndsWith("'")

            if ($hasDoubleQuotes -or $hasSingleQuotes) {
                $value = $value.Substring(1, $value.Length - 2)
            }
        }

        [Environment]::SetEnvironmentVariable($key, $value, "Process")
        $script:DotenvImported[$key] = $value
    }
}

function Get-ConfigValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ""
    )

    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        $source = "Process"
        if ($script:DotenvImported.ContainsKey($Name) -and $script:DotenvImported[$Name] -eq $processValue) {
            $source = ".env->Process"
        }

        return @{
            Value = $processValue
            Source = $source
        }
    }

    $userValue = [Environment]::GetEnvironmentVariable($Name, "User")
    if (-not [string]::IsNullOrWhiteSpace($userValue)) {
        return @{
            Value = $userValue
            Source = "User"
        }
    }

    return @{
        Value = $Default
        Source = "Default"
    }
}

try {
    Import-DotenvToProcess

    Write-Log "START user=$([Environment]::UserName) machine=$env:COMPUTERNAME"
    Write-Log "ProjectRoot exists=$(Test-Path $ProjectRoot)"
    Write-Log "PythonExe exists=$(Test-Path $PythonExe)"
    Write-Log "Dotenv exists=$(Test-Path $DotenvPath)"
    Write-Log "Dotenv imported keys=$(([string[]]$DotenvImported.Keys | Sort-Object) -join ',')"

    if (-not (Test-Path $ProjectRoot)) {
        throw "ProjectRoot não encontrado: $ProjectRoot"
    }

    if (-not (Test-Path $PythonExe)) {
        throw "PythonExe não encontrado: $PythonExe"
    }

    Set-Location $ProjectRoot
    Write-Log "PWD=$((Get-Location).Path)"

    $healthJson = (& $PythonExe scripts/healthcheck.py --config $ConfigPath 2>&1 | Out-String).Trim()
    $healthExitCode = $LASTEXITCODE

    Write-Log "healthcheck exitcode=$healthExitCode"
    Write-Log "healthcheck output=$healthJson"

    if ($healthExitCode -ne 0) {
        throw "healthcheck.py falhou: $healthJson"
    }

    if ([string]::IsNullOrWhiteSpace($healthJson)) {
        throw "healthcheck.py não retornou JSON"
    }

    $health = $healthJson | ConvertFrom-Json

    $problemCodes = @()
    if ($health.issues) {
        $problemCodes = @($health.issues | ForEach-Object { $_.code })
    }

    $shouldAlert =
        ($health.status -ne "ok") -or
        ($problemCodes -contains "paused") -or
        ($problemCodes -contains "no_market_cache") -or
        ($problemCodes -contains "live_reconcile_required")

    Write-Log "status=$($health.status) shouldAlert=$shouldAlert issues=$($problemCodes -join ',')"

    if (-not $shouldAlert) {
        Write-Log "WATCHDOG_OK"
        Write-Host "WATCHDOG_OK"
        exit 0
    }

    $serverConfig = Get-ConfigValue -Name "NTFY_SERVER" -Default "https://ntfy.sh"
    $topicConfig = Get-ConfigValue -Name "NTFY_TOPIC"
    $tokenConfig = Get-ConfigValue -Name "NTFY_TOKEN"
    $usernameConfig = Get-ConfigValue -Name "NTFY_USERNAME"
    $passwordConfig = Get-ConfigValue -Name "NTFY_PASSWORD"

    $server = $serverConfig.Value
    $topic = $topicConfig.Value
    $token = $tokenConfig.Value
    $username = $usernameConfig.Value
    $password = $passwordConfig.Value

    Write-Log "server=$server server_source=$($serverConfig.Source)"
    Write-Log "topic_present=$(-not [string]::IsNullOrWhiteSpace($topic)) topic_source=$($topicConfig.Source)"
    Write-Log "token_present=$(-not [string]::IsNullOrWhiteSpace($token)) token_source=$($tokenConfig.Source)"
    Write-Log "user_present=$(-not [string]::IsNullOrWhiteSpace($username)) user_source=$($usernameConfig.Source)"

    if ([string]::IsNullOrWhiteSpace($topic)) {
        throw "NTFY_TOPIC precisa estar definido no ambiente, no .env ou nas variáveis de usuário"
    }

    $uri = "$($server.TrimEnd('/'))/$topic"
    Write-Log "uri=$uri"

    $bodyLines = @(
        "Projeto: USDTBRL"
        "Status: $($health.status)"
        "Modo: $($health.mode)"
        "Paused: $($health.paused)"
        "Live reconcile required: $($health.live_reconcile_required)"
        "Active dispatch locks: $($health.active_dispatch_locks)"
        "Issues: $($problemCodes -join ', ')"
        "Checked at: $($health.checked_at)"
    )

    if ($health.runtime_cache_file) {
        $bodyLines += "Runtime cache: $($health.runtime_cache_file)"
    }

    if ($health.market_cache_file) {
        $bodyLines += "Market cache: $($health.market_cache_file)"
    }

    $body = $bodyLines -join "`n"

    $headers = @{
        "Title" = "USDTBRL alerta operacional"
        "Tags" = "warning,robot,chart_with_upwards_trend"
        "Priority" = "high"
    }

    if (-not [string]::IsNullOrWhiteSpace($token)) {
        $headers["Authorization"] = "Bearer $token"
        Write-Log "auth_mode=Bearer"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($username) -and -not [string]::IsNullOrWhiteSpace($password)) {
        $pair = "$username`:$password"
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pair))
        $headers["Authorization"] = "Basic $encoded"
        Write-Log "auth_mode=Basic"
    }
    else {
        Write-Log "auth_mode=None"
    }

    $params = @{
        Method = "POST"
        Uri = $uri
        Headers = $headers
        Body = $body
        ContentType = "text/plain; charset=utf-8"
    }

    Invoke-RestMethod @params | Out-Null

    Write-Log "WATCHDOG_ALERT_SENT"
    Write-Host "WATCHDOG_ALERT_SENT"
    exit 0
}
catch {
    Write-Log "ERROR=$($_.Exception.Message)"
    Write-Log "DETAIL=$($_ | Out-String)"
    exit 1
}