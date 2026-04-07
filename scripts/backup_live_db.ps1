$ErrorActionPreference = "Stop"

$source = ".\data\usdtbrl_live_100usdt.sqlite"
$backupDir = ".\data\backups"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

if (-not (Test-Path $source)) {
    Write-Host "DB não encontrado: $source"
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$destination = Join-Path $backupDir "usdtbrl_live_100usdt_$timestamp.sqlite"

Copy-Item $source $destination -Force

Write-Host "BACKUP_OK $destination"