<#
.SYNOPSIS
    Lance File2EDI sur une VM Azure apres clone du repo.

.DESCRIPTION
    - Charge les variables depuis .env.vm (cree depuis .env.vm.example).
    - Verifie le build frontend et le construit si necessaire.
    - Demarre l'API FastAPI avec des valeurs adaptees a un usage VM + n8n.

.EXAMPLE
    ./run_vm.ps1
    ./run_vm.ps1 -RebuildFrontend
#>
[CmdletBinding()]
param(
    [switch]$RebuildFrontend
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$envFile = Join-Path $PSScriptRoot '.env.vm'
if (-not (Test-Path $envFile)) {
    Write-Host "[run_vm] .env.vm introuvable — copie depuis .env.vm.example" -ForegroundColor Yellow
    Copy-Item (Join-Path $PSScriptRoot '.env.vm.example') $envFile
    Write-Host "[run_vm] Editez .env.vm puis relancez ce script." -ForegroundColor Yellow
    exit 1
}

Write-Host "[run_vm] Chargement de .env.vm" -ForegroundColor Cyan
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line.Contains('=')) {
        $idx = $line.IndexOf('=')
        $name = $line.Substring(0, $idx).Trim()
        $value = $line.Substring($idx + 1).Trim()
        if ($name) {
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

$distIndex = Join-Path $PSScriptRoot 'frontend/dist/index.html'
if ($RebuildFrontend -or -not (Test-Path $distIndex)) {
    Write-Host "[run_vm] Build du frontend" -ForegroundColor Cyan
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        if (-not (Test-Path 'node_modules')) {
            npm install
        }
        npm run build
    } finally {
        Pop-Location
    }
}

$hostValue = if ($env:APP_HOST) { $env:APP_HOST } else { '127.0.0.1' }
$portValue = if ($env:APP_PORT) { [int]$env:APP_PORT } else { 8000 }

Write-Host ""
Write-Host "  Environnement VM File2EDI" -ForegroundColor Green
Write-Host "  ───────────────────────" -ForegroundColor Green
Write-Host "  APP_HOST               : $hostValue"
Write-Host "  APP_PORT               : $portValue"
Write-Host "  APP_REQUIRE_AUTH       : $(if ($env:APP_REQUIRE_AUTH) { $env:APP_REQUIRE_AUTH } else { '(auto)' })"
Write-Host "  APP_API_KEYS configuree: $(if ($env:APP_API_KEYS -or $env:N8N_API_KEY) { 'oui' } else { 'non' })"
Write-Host "  APP_API_ROLE           : $(if ($env:APP_API_ROLE) { $env:APP_API_ROLE } else { 'adv' })"
Write-Host "  URL API                : http://$hostValue`:$portValue"
Write-Host ""

python -m uvicorn server:app --host $hostValue --port $portValue