#!/usr/bin/env pwsh
# Build File2EDI React frontend and optionally start Docker Compose
param(
    [switch]$Docker,
    [switch]$SkipNpm
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $SkipNpm) {
    Write-Host ">> Building React frontend..."
    Push-Location frontend
    if (-not (Test-Path node_modules)) { npm install }
    npm run build
    Pop-Location
    Write-Host ">> Frontend built to frontend/dist"
}

if ($Docker) {
    Write-Host ">> Starting Docker Compose..."
    docker compose -f docker-compose.file2edi.yml up --build -d
    Write-Host ">> File2EDI: http://localhost:8080"
} else {
    Write-Host ">> Start with: uvicorn server:app --host 0.0.0.0 --port 8000"
    Write-Host ">> UI: http://localhost:8000"
}
