<#
.SYNOPSIS
    Lance File2EDI en local avec la même expérience que sur Databricks Apps.

.DESCRIPTION
    - Charge les variables depuis .env.local (créé depuis .env.local.example).
    - Vérifie le build frontend (frontend/dist) et le construit si absent.
    - Choisit un port libre.
    - Démarre uvicorn avec l'identité/les rôles/le LLM configurés.

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

# ── 1. Charger .env.local ────────────────────────────────────────────────────
$envFile = Join-Path $PSScriptRoot '.env.local'
if (-not (Test-Path $envFile)) {
    Write-Host "[run_local] .env.local introuvable — copie depuis .env.local.example" -ForegroundColor Yellow
    Copy-Item (Join-Path $PSScriptRoot '.env.local.example') $envFile
    Write-Host "[run_local] Editez .env.local puis relancez ce script." -ForegroundColor Yellow
    exit 1
}

Write-Host "[run_local] Chargement de .env.local" -ForegroundColor Cyan
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $name = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
}

# ── 2. Vérifier le build frontend ────────────────────────────────────────────
$distIndex = Join-Path $PSScriptRoot 'frontend/dist/index.html'
if ($Rebuild -or -not (Test-Path $distIndex)) {
    Write-Host "[run_local] Build du frontend (frontend/dist manquant ou -Rebuild)" -ForegroundColor Cyan
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        if (-not (Test-Path 'node_modules')) { npm install }
        npm run build
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[run_local] frontend/dist présent — build ignoré (-Rebuild pour forcer)" -ForegroundColor DarkGray
}

# ── 3. Choisir un port libre ─────────────────────────────────────────────────
function Test-PortFree([int]$p) {
    -not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}
if ($Port -eq 0) {
    $Port = 8000
    while (-not (Test-PortFree $Port)) { $Port++ }
} elseif (-not (Test-PortFree $Port)) {
    Write-Host "[run_local] Port $Port occupé — recherche d'un port libre" -ForegroundColor Yellow
    while (-not (Test-PortFree $Port)) { $Port++ }
}

# ── 4. Récapitulatif ─────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Environnement local File2EDI" -ForegroundColor Green
Write-Host "  ─────────────────────────────" -ForegroundColor Green
Write-Host "  DEV_ACTOR              : $($env:DEV_ACTOR)"
Write-Host "  DATABRICKS_CONFIG_PROFILE : $($env:DATABRICKS_CONFIG_PROFILE)"
Write-Host "  APP_REQUIRE_AUTH       : $(if ($env:APP_REQUIRE_AUTH) { $env:APP_REQUIRE_AUTH } else { '(auto)' })"
Write-Host "  URL                    : http://127.0.0.1:$Port"
Write-Host ""

# ── 5. Lancer uvicorn ────────────────────────────────────────────────────────
python -m uvicorn server:app --host 127.0.0.1 --port $Port --reload
