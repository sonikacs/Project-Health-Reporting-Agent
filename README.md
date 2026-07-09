# Project Health Reporting Agent

This project implements Phase 2 of the assignment: a project health agent that reads Excel project plans, calculates RAG status, and writes weekly health reports with plain-English reasoning.

## Design Decisions

The RAG decision is deterministic and auditable. The agent does not ask an LLM to guess the project status from raw spreadsheet rows. Instead, it parses the workbook, calculates schedule, milestone, completion, blocker, and data-quality signals, applies rules from `rag_methodology.md`, then generates a clear report.

The implementation uses an additive point-based version of the methodology weights so each risk signal remains auditable in the generated reasoning. The scoring categories still map to the methodology: schedule slippage, milestone health, execution progress, blockers/comments, and unavailable budget data.

The LLM layer is implemented and enabled by default. After deterministic scoring, the agent calls Gemini using `GEMINI_API_KEY` to write the plain-English reasoning and recommendations. Transient provider errors such as rate limits or high-demand HTTP 500/503 responses are retried before falling back. If no key is configured, the LLM call still fails after retry, or `--disable-llm` is passed, the agent logs the issue and falls back to deterministic template narrative so the weekly run still completes.

## Files

- `rag_methodology.md` - Phase 1 one-page RAG framework.
- `project_health_agent.py` - Thin backward-compatible CLI wrapper.
- `health_agent/` - Production-style Python package for parsing, scoring, rendering, and CLI orchestration.
- `monthly_presentation_generator.mjs` - Phase 3 monthly executive deck generator.
- `generate_weekly_reports.ps1` - Convenience wrapper for weekly runs on Windows.
- `generate_monthly_presentation.ps1` - Convenience wrapper for monthly deck generation.
- `create_submission_package.ps1` - Creates a clean reviewer-facing submission folder.
- `requirements.txt` - Python dependency list.
- `outputs/weekly/YYYY-MM-DD/` - Dated weekly reports generated from the provided project plans.
- `outputs/monthly/YYYY-MM/` - Monthly executive presentation, manifest, and previews.
- `logs/` - Weekly and monthly run logs.

## How To Run

### Quick End-To-End Test

From PowerShell:

```powershell
cd "C:\Users\sonik\OneDrive\Documents\bs1"
$env:GEMINI_API_KEY = "your_gemini_api_key_here"
.\generate_weekly_reports.ps1 -RunDate 2026-07-09
.\generate_monthly_presentation.ps1 -Month 2026-07
start outputs\monthly\2026-07\project_health_monthly_synthesis.pptx
```

Check logs:

```powershell
Get-Content logs\weekly_agent_2026-07-09.log -Tail 20
Get-Content logs\monthly_presentation_2026-07.log -Tail 20
```

Create a clean submission folder with only reviewer-facing files:

```powershell
.\create_submission_package.ps1 -RunDate 2026-07-09 -Month 2026-07
```

This writes:

- `submission/rag_methodology.md`
- `submission/README.md`
- `submission/code/`
- `submission/weekly_outputs/YYYY-MM-DD/*.md`
- `submission/monthly_presentation/project_health_monthly_synthesis.pptx`

### Run Weekly Agent Directly

Use the bundled Python runtime available in this Codex workspace:

```powershell
& "C:\Users\sonik\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" project_health_agent.py `
  "C:\Users\sonik\Downloads\Project Plan B.xlsx" `
  "C:\Users\sonik\Downloads\S2P Project (1).xlsx" `
  --output-dir outputs\weekly\2026-07-09 `
  --run-date 2026-07-09 `
  --log-dir logs
```

Or run the helper:

```powershell
.\generate_weekly_reports.ps1
```

To run with Gemini narrative generation:

```powershell
$env:GEMINI_API_KEY = "your_gemini_api_key_here"
.\generate_weekly_reports.ps1 -RunDate 2026-07-09
```

To force a non-LLM run:

```powershell
.\generate_weekly_reports.ps1 -RunDate 2026-07-09 -DisableLlm
```

To override the LLM provider/model:

```powershell
.\generate_weekly_reports.ps1 -RunDate 2026-07-09 -LlmProvider gemini -LlmModel gemini-3.5-flash
```

The LLM does not decide the RAG color or score. It writes the reasoning and recommendations after the rule engine has already produced the project health assessment.

The agent writes one Markdown report and one JSON report per project, plus a portfolio summary:

- `outputs/weekly/YYYY-MM-DD/Zycus_-_UniSan_S2P_Implementation_weekly_health.md`
- `outputs/weekly/YYYY-MM-DD/Zycus_-_Titan_S2P_Implementation_weekly_health.md`
- `outputs/weekly/YYYY-MM-DD/portfolio_weekly_summary.md`
- `outputs/weekly/YYYY-MM-DD/run_manifest.json`
- `logs/weekly_agent_YYYY-MM-DD.log`

The submission packager copies only the Markdown weekly reports into `submission/weekly_outputs/`, grouped by run date. JSON manifests and raw run logs stay out of the final handoff package.

## Weekly Scheduling

Windows Task Scheduler example:

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File C:\Users\sonik\OneDrive\Documents\bs1\generate_weekly_reports.ps1"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -TaskName "Project Health Weekly Agent" -Action $action -Trigger $trigger
```

Linux/macOS cron equivalent:

```cron
0 9 * * MON cd /path/to/project && python project_health_agent.py "/path/to/Project Plan B.xlsx" "/path/to/S2P Project (1).xlsx" --output-dir outputs/weekly/$(date +\%F) --run-date $(date +\%F) --log-dir logs
```

## Generate The Monthly Executive Deck

After weekly reports exist, run:

```powershell
.\generate_monthly_presentation.ps1
```

The monthly wrapper reads the latest dated weekly folder under `outputs/weekly/` and writes:

- `outputs/monthly/YYYY-MM/project_health_monthly_synthesis.pptx`
- `outputs/monthly/YYYY-MM/monthly_manifest.json`
- `logs/monthly_presentation_YYYY-MM.log`

The generated deck is a 6-slide executive synthesis:

1. Portfolio situation and headline ask
2. Project health comparison
3. Near-term execution trend
4. Emerging risks
5. Project-level evidence
6. Recommended recovery cadence

## Current Sample Result

Both sample project plans are rated Red by the current methodology:

- UniSan: Red due to Red summary schedule health, High risk, overdue open work, and many near-term risky tasks.
- Titan: Red due to overdue open work, on-hold tasks, High risk, dependency comments, and near-term risky tasks, even though the workbook summary schedule health is Green.

## Data Handling

The agent handles messy input by:

- Detecting the main project sheet automatically.
- Reading `Summary` and `Comments` sheets when available.
- Ignoring unparseable dates rather than crashing.
- Reporting missing or unavailable fields in the data-quality notes.
- Excluding budget burn from the score when no budget fields exist.
- Writing dated output folders so weekly runs are retained for trend analysis.
- Writing run logs and manifests for auditability.
