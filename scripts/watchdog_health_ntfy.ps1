$ErrorActionPreference = "Stop"

$ProjectRoot = "E:\USDTBRL"
$ConfigPath = "config/config.yml"
$PythonExe = "E:\USDTBRL\.venv\Scripts\python.exe"

Set-Location $ProjectRoot

$healthJson = & $PythonExe scripts/healthcheck.py --config $ConfigPath
if (-not $healthJson) {
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

if (-not $shouldAlert) {
    Write-Host "WATCHDOG_OK"
    exit 0
}

$topic = $env:NTFY_TOPIC
$server = $env:NTFY_SERVER
$token = $env:NTFY_TOKEN
$username = $env:NTFY_USERNAME
$password = $env:NTFY_PASSWORD

if ([string]::IsNullOrWhiteSpace($server) -or [string]::IsNullOrWhiteSpace($topic)) {
    throw "NTFY_SERVER e NTFY_TOPIC precisam estar definidos no ambiente"
}

$uri = "$server/$topic"

$bodyLines = @(
    "Projeto: USDTBRL",
    "Status: $($health.status)",
    "Modo: $($health.mode)",
    "Paused: $($health.paused)",
    "Live reconcile required: $($health.live_reconcile_required)",
    "Active dispatch locks: $($health.active_dispatch_locks)",
    "Issues: $($problemCodes -join ', ')",
    "Checked at: $($health.checked_at)"
)

if ($health.runtime_cache_file) {
    $bodyLines += "Runtime cache: $($health.runtime_cache_file)"
}
if ($health.market_cache_file) {
    $bodyLines += "Market cache: $($health.market_cache_file)"
}

$body = ($bodyLines -join "`n")

$headers = @{
    "Title"    = "USDTBRL alerta operacional"
    "Tags"     = "warning,robot,chart_with_upwards_trend"
    "Priority" = "high"
}

if (-not [string]::IsNullOrWhiteSpace($token)) {
    $headers["Authorization"] = "Bearer $token"
}

$params = @{
    Method      = "POST"
    Uri         = $uri
    Headers     = $headers
    Body        = $body
    ContentType = "text/plain; charset=utf-8"
}

if (-not [string]::IsNullOrWhiteSpace($username) -and -not [string]::IsNullOrWhiteSpace($password)) {
    $secure = ConvertTo-SecureString $password -AsPlainText -Force
    $cred = New-Object System.Management.Automation.PSCredential ($username, $secure)
    $params["Credential"] = $cred
}

Invoke-RestMethod @params | Out-Null
Write-Host "WATCHDOG_ALERT_SENT"