# Install Windows Task Scheduler task for EDIFACT Orders Generator
# Run as Administrator

$ErrorActionPreference = "Stop"

$TaskName = "EDIFACT_Orders_Generator"
$ExePath = "\\\\dy00fs04.emea.bosch.com\\Dy2_Sales$\\Pole Data\\EDIPUSHBOT\\edifact_generator\\EDIFACT_Orders_Generator.exe"
$WorkingDir = "\\\\dy00fs04.emea.bosch.com\\Dy2_Sales$\\Pole Data\\EDIPUSHBOT\\edifact_generator"

Write-Host "[INFO] Creating Task Scheduler task: $TaskName"

# Remove existing task if present
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "[INFO] Removed existing task."
}

# Action
$Action = New-ScheduledTaskAction `
    -Execute $ExePath `
    -WorkingDirectory $WorkingDir

# Trigger: every 5 minutes
$Trigger = New-ScheduledTaskTrigger `
    -RepetitionInterval (New-TimeSpan -Minutes 5) `
    -RepetitionDuration ([TimeSpan]::MaxValue) `
    -Once `
    -At "07:00"

# Settings
$Settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10) `
    -RunOnlyIfNetworkAvailable `
    -Priority 5

# Principal: run whether logged on or not, with highest privileges
$Principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Register
Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Principal $Principal `
    -Description "EDIFACT Orders Generator - ELM_STANDARD only - Bosch HC/SFR-BI"

Write-Host "[SUCCESS] Task '$TaskName' registered."
Write-Host "[INFO] Working directory: $WorkingDir"
Write-Host "[INFO] IMPORTANT: Set SFTP_HOST, SFTP_USERNAME, SFTP_PASSWORD (or SFTP_PRIVATE_KEY_PATH), SFTP_REMOTE_DIR as system environment variables."
