@'
$ErrorActionPreference = "Stop"

$taskName = "USDTBRL_Watchdog_Health_NTFY"
$scriptPath = "E:\USDTBRL\scripts\watchdog_health_ntfy.ps1"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File $scriptPath"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Description "Watchdog de healthcheck com alerta NTFY para USDTBRL" -Force
Write-Host "TASK_OK $taskName"
'@ | Set-Content .\scripts\install_watchdog_health_ntfy.ps1 -Encoding UTF8