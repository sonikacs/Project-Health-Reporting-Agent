param(
    [string[]]$ProjectFiles = @(
        "C:\Users\sonik\Downloads\Project Plan B.xlsx",
        "C:\Users\sonik\Downloads\S2P Project (1).xlsx"
    ),
    [string]$OutputRoot = "outputs\weekly",
    [string]$RunDate = (Get-Date -Format "yyyy-MM-dd"),
    [string]$LogDir = "logs",
    [switch]$DisableLlm,
    [string]$LlmProvider = "gemini",
    [string]$LlmModel = "gemini-3.5-flash"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$python = "C:\Users\sonik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$outputDir = Join-Path $OutputRoot $RunDate

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$agentArgs = @("project_health_agent.py") + $ProjectFiles + @(
    "--output-dir", $outputDir,
    "--run-date", $RunDate,
    "--log-dir", $LogDir,
    "--llm-provider", $LlmProvider,
    "--llm-model", $LlmModel
)
if ($DisableLlm) {
    $agentArgs += @("--disable-llm")
}

& $python @agentArgs
