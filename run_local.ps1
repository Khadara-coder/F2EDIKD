<#
.SYNOPSIS
    Launch File2EDI locally with a Databricks-like experience.

.DESCRIPTION
    - Loads environment variables from .env.local (.env.local.example on first run).
    - Ensures frontend build exists (frontend/dist) and builds when missing.
    - Picks a free local port.
    - Starts uvicorn with local identity and auth settings.

.EXAMPLE
    ./run_local.ps1
    ./run_local.ps1 -Port 8020 -Rebuild
#>
[CmdletBinding()]
param(
    [int]$Port = 0,
    [switch]$Rebuild
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Stop-EdifactInstances {
    $listen = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -ge 8000 -and $_.LocalPort -le 8100 } |
        Select-Object -ExpandProperty OwningProcess -Unique

    $uvicorn = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @('python.exe', 'py.exe') -and
            $_.CommandLine -and
            $_.CommandLine -match 'uvicorn.+server:app'
        } |
        Select-Object -ExpandProperty ProcessId -Unique

    $candidatePids = @($listen + $uvicorn | Sort-Object -Unique)
    $stopped = @()

    foreach ($procId in $candidatePids) {
        if (-not $procId) { continue }
        try {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
            if (-not $proc) { continue }
            $cmd = [string]$proc.CommandLine
            $isEdifact = $cmd -match 'server:app' -or $cmd -match 'EDIFACT'
            if (-not $isEdifact) { continue }
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            $stopped += $procId
        } catch {
            continue
        }
    }

    if ($stopped.Count -gt 0) {
        Write-Host ("[run_local] Stopped existing EDIFACT instance(s): {0}" -f (($stopped | Sort-Object -Unique) -join ', ')) -ForegroundColor Yellow
    }
}

# 1. Load .env.local
$envFile = Join-Path $PSScriptRoot '.env.local'
if (-not (Test-Path $envFile)) {
    Write-Host "[run_local] .env.local missing - copying from .env.local.example" -ForegroundColor Yellow
    Copy-Item (Join-Path $PSScriptRoot '.env.local.example') $envFile
    Write-Host "[run_local] Edit .env.local then run this script again." -ForegroundColor Yellow
    exit 1
}

Write-Host "[run_local] Loading .env.local" -ForegroundColor Cyan
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $name = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
}

# 2. Ensure frontend build
$distIndex = Join-Path $PSScriptRoot 'frontend/dist/index.html'
if ($Rebuild -or -not (Test-Path $distIndex)) {
    Write-Host "[run_local] Building frontend (missing frontend/dist or -Rebuild)" -ForegroundColor Cyan
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        if (-not (Test-Path 'node_modules')) { npm install }
        npm run build
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[run_local] frontend/dist present - build skipped (use -Rebuild to force)" -ForegroundColor DarkGray
}

# 3. Stop previous EDIFACT instances
Stop-EdifactInstances

# 4. Pick a free port
function Test-PortFree([int]$p) {
    -not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}
if ($Port -eq 0) {
    $Port = 8000
    while (-not (Test-PortFree $Port)) { $Port++ }
} elseif (-not (Test-PortFree $Port)) {
    Write-Host "[run_local] Port $Port busy - searching a free port" -ForegroundColor Yellow
    while (-not (Test-PortFree $Port)) { $Port++ }
}

# 5. Summary
Write-Host ""
Write-Host "  Local File2EDI environment" -ForegroundColor Green
Write-Host "  ---------------------------" -ForegroundColor Green
Write-Host "  DEV_ACTOR              : $($env:DEV_ACTOR)"
Write-Host "  DATABRICKS_CONFIG_PROFILE : $($env:DATABRICKS_CONFIG_PROFILE)"
Write-Host "  APP_REQUIRE_AUTH       : $(if ($env:APP_REQUIRE_AUTH) { $env:APP_REQUIRE_AUTH } else { '(auto)' })"
Write-Host "  URL                    : http://127.0.0.1:$Port"
Write-Host ""

# 6. Start uvicorn
python -m uvicorn server:app --host 127.0.0.1 --port $Port --reload
