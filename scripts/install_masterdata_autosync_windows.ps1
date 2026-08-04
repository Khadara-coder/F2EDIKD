#Requires -Version 5.1
<#
.SYNOPSIS
  Install a Windows Scheduled Task that syncs masterdata.git every day.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\install_masterdata_autosync_windows.ps1
#>

param(
  [string]$RepoUrl = "https://github.boschdevcloud.com/RSR1DY/masterdata.git",
  [string]$Branch = "main",
  [string]$TargetDir = "",
  [string]$NotifyApiUrl = "http://127.0.0.1:8000/api/masterdata/sync",
  [string]$NotifyApiKey = "",
  [string]$Time = "02:15",
  [string]$TaskName = "File2EDI-Masterdata-AutoSync"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $TargetDir) {
  $TargetDir = Join-Path $Root "data\masterdata"
}

$PythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $PythonCmd) {
  throw "python introuvable dans PATH"
}
$Python = $PythonCmd.Source

$Script = Join-Path $Root "scripts\sync_masterdata_repo.py"
if (-not (Test-Path $Script)) {
  throw "Script introuvable: $Script"
}

$Args = @(
  "`"$Script`"",
  "--repo-url", "`"$RepoUrl`"",
  "--branch", "`"$Branch`"",
  "--target-dir", "`"$TargetDir`""
)
if ($NotifyApiUrl) {
  $Args += @("--notify-api-url", "`"$NotifyApiUrl`"")
}
if ($NotifyApiKey) {
  $Args += @("--notify-api-key", "`"$NotifyApiKey`"")
}

$Argument = ($Args -join " ")
$Action = New-ScheduledTaskAction -Execute $Python -Argument $Argument -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null

Write-Host "OK: tache planifiee '$TaskName' chaque jour a $Time"
Write-Host "  python $Script"
Write-Host "  target: $TargetDir"
Write-Host "  notify: $NotifyApiUrl"
Write-Host ""
Write-Host "Lancer maintenant:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
