param(
    [string]$WeeklyRoot = "outputs\weekly",
    [string]$Month = (Get-Date -Format "yyyy-MM"),
    [string]$OutputRoot = "outputs\monthly",
    [string]$LogDir = "logs"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$node = "C:\Users\sonik\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
if (-not (Test-Path $node)) {
    $node = "node"
}

$env:HOME = "C:\Users\sonik"

$monthlyDir = Join-Path $OutputRoot $Month
$deckPath = Join-Path $monthlyDir "project_health_monthly_synthesis.pptx"
$previewDir = Join-Path $monthlyDir "preview"

New-Item -ItemType Directory -Force -Path $monthlyDir | Out-Null
New-Item -ItemType Directory -Force -Path $previewDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

& $node "monthly_presentation_generator.mjs" --input $WeeklyRoot --month $Month --output $deckPath --previewDir $previewDir --logDir $LogDir
