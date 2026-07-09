param(
    [string]$RunDate = "2026-07-09",
    [string]$Month = "2026-07",
    [string]$SubmissionDir = "submission"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$weeklyDir = Join-Path "outputs\weekly" $RunDate
$weeklyRoot = "outputs\weekly"
$monthlyDir = Join-Path "outputs\monthly" $Month

if (-not (Test-Path $weeklyRoot)) {
    throw "Weekly output root not found: $weeklyRoot. Run .\generate_weekly_reports.ps1 first."
}

if (-not (Test-Path $monthlyDir)) {
    throw "Monthly output folder not found: $monthlyDir. Run .\generate_monthly_presentation.ps1 -Month $Month first."
}

New-Item -ItemType Directory -Force -Path $SubmissionDir | Out-Null
New-Item -ItemType Directory -Force -Path "$SubmissionDir\code" | Out-Null
New-Item -ItemType Directory -Force -Path "$SubmissionDir\weekly_outputs" | Out-Null
New-Item -ItemType Directory -Force -Path "$SubmissionDir\monthly_presentation" | Out-Null

Get-ChildItem "$SubmissionDir\weekly_outputs" -Force | Remove-Item -Recurse -Force

Copy-Item "rag_methodology.md" "$SubmissionDir\rag_methodology.md" -Force
Copy-Item "README.md" "$SubmissionDir\README.md" -Force
Copy-Item "requirements.txt" "$SubmissionDir\requirements.txt" -Force
Copy-Item "project_health_agent.py" "$SubmissionDir\code\project_health_agent.py" -Force
Copy-Item "monthly_presentation_generator.mjs" "$SubmissionDir\code\monthly_presentation_generator.mjs" -Force
Copy-Item "generate_weekly_reports.ps1" "$SubmissionDir\code\generate_weekly_reports.ps1" -Force
Copy-Item "generate_monthly_presentation.ps1" "$SubmissionDir\code\generate_monthly_presentation.ps1" -Force

New-Item -ItemType Directory -Force -Path "$SubmissionDir\code\health_agent" | Out-Null
Get-ChildItem "health_agent" -Filter "*.py" | Copy-Item -Destination "$SubmissionDir\code\health_agent" -Force

$weeklyFolders = Get-ChildItem $weeklyRoot -Directory | Sort-Object Name
foreach ($folder in $weeklyFolders) {
    $markdownReports = Get-ChildItem $folder.FullName -Filter "*.md"
    if ($markdownReports.Count -eq 0) {
        continue
    }
    $datedSubmissionDir = Join-Path "$SubmissionDir\weekly_outputs" $folder.Name
    New-Item -ItemType Directory -Force -Path $datedSubmissionDir | Out-Null
    $markdownReports | Copy-Item -Destination $datedSubmissionDir -Force
}

Copy-Item "$monthlyDir\project_health_monthly_synthesis.pptx" "$SubmissionDir\monthly_presentation\project_health_monthly_synthesis.pptx" -Force

Write-Information "Clean submission package written to $SubmissionDir" -InformationAction Continue
