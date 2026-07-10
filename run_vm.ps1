[CmdletBinding()]
param(
    [switch]$RebuildFrontend
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

$envFile = Join-Path $PSScriptRoot '.env.vm'
if (-not (Test-Path $envFile)) {
    Write-Host '[run_vm] .env.vm missing - copying from .env.vm.example' -ForegroundColor Yellow
    Copy-Item (Join-Path $PSScriptRoot '.env.vm.example') $envFile
    Write-Host '[run_vm] Edit .env.vm then run the script again.' -ForegroundColor Yellow
    exit 1
}

Write-Host '[run_vm] Loading .env.vm' -ForegroundColor Cyan
foreach ($rawLine in Get-Content $envFile) {
    $line = $rawLine.Trim()
    if (-not $line) { continue }
    if ($line.StartsWith('#')) { continue }
    if (-not $line.Contains('=')) { continue }

    $idx = $line.IndexOf('=')
    $name = $line.Substring(0, $idx).Trim()
    $value = $line.Substring($idx + 1).Trim()
    if ($name) {
        Set-Item -Path ("Env:{0}" -f $name) -Value $value
    }
}

$distIndex = Join-Path $PSScriptRoot 'frontend/dist/index.html'
if ($RebuildFrontend -or -not (Test-Path $distIndex)) {
    Write-Host '[run_vm] Building frontend' -ForegroundColor Cyan
    Push-Location (Join-Path $PSScriptRoot 'frontend')
    try {
        if (-not (Test-Path 'node_modules')) {
            npm install
        }
        npm run build
    }
    finally {
        Pop-Location
    }
}

$hostValue = if ($env:APP_HOST) { $env:APP_HOST } else { '127.0.0.1' }
$portValue = if ($env:APP_PORT) { [int]$env:APP_PORT } else { 8000 }
$requireAuth = if ($env:APP_REQUIRE_AUTH) { $env:APP_REQUIRE_AUTH } else { '(auto)' }
$apiKeyConfigured = if ($env:APP_API_KEYS -or $env:N8N_API_KEY) { 'yes' } else { 'no' }
$apiRole = if ($env:APP_API_ROLE) { $env:APP_API_ROLE } else { 'adv' }

Write-Host ''
Write-Host '  VM File2EDI environment' -ForegroundColor Green
Write-Host '  ------------------------' -ForegroundColor Green
Write-Host ("  APP_HOST               : {0}" -f $hostValue)
Write-Host ("  APP_PORT               : {0}" -f $portValue)
Write-Host ("  APP_REQUIRE_AUTH       : {0}" -f $requireAuth)
Write-Host ("  APP_API_KEYS configured: {0}" -f $apiKeyConfigured)
Write-Host ("  APP_API_ROLE           : {0}" -f $apiRole)
Write-Host ("  API URL                : http://{0}:{1}" -f $hostValue, $portValue)
Write-Host ''

python -m uvicorn server:app --host $hostValue --port $portValue