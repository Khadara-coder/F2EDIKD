param(
    [switch]$Update,
    [switch]$NoViz,
    [switch]$WithSemantic,
    [string]$GraphifyProject = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
$graphifyRoot = if ($GraphifyProject) {
    (Resolve-Path $GraphifyProject).Path
} else {
    (Resolve-Path (Join-Path $repoRoot "..\graphify")).Path
}
$outputDir = Join-Path $repoRoot "reports\graphify-out"

if (-not (Test-Path (Join-Path $graphifyRoot "pyproject.toml"))) {
    throw "Projet graphify introuvable: $graphifyRoot"
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
$env:GRAPHIFY_OUT = $outputDir

$arguments = @("run", "--project", $graphifyRoot, "graphify", $repoRoot)
if ($Update) {
    $arguments += "--update"
}
if ($NoViz) {
    $arguments += "--no-viz"
}
if (-not $WithSemantic) {
    $arguments += "--code-only"
}

Write-Host "Analyse graphify de $repoRoot"
Write-Host "Sortie: $outputDir"
& uv @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host "Analyse graphify terminee."