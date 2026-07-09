# Project Health RAG Methodology

## Purpose

The weekly project health report classifies each project as Green, Amber, or Red based on delivery risk. The rating is intended for executive review, so it combines measurable plan data with plain-English risk interpretation instead of simply repeating the project plan's existing color.

## Available Signals and Assumptions

The sample project plans provide task-level status, start and end dates, percent complete, schedule health, at-risk flags, project stage, project manager, summary completion counts, and comments. Budget fields are not present in the provided workbooks, so budget burn is treated as "unknown" and does not directly change the RAG score unless future data includes planned budget, actual spend, or burn rate. Stakeholder sentiment is inferred only from comment language and blocker wording; it should be considered a weak signal unless formal survey or meeting sentiment data is added.

The framework assumes the workbook's "Today" date is the reporting date when present. If missing, the agent uses the run date. Incomplete or unparseable fields are not treated as automatic failures; they reduce confidence and are called out in the reasoning.

## RAG Decision Framework

### Green

A project is Green when delivery appears on track and no material intervention is required. Typical indicators are: summary schedule health is Green; fewer than 10% of active tasks are Red or Yellow; overdue open tasks are minimal or low impact; no critical milestones are blocked; comments do not indicate unresolved dependency, customer, data, or decision risks; and project progress is broadly consistent with elapsed timeline.

### Amber

A project is Amber when delivery is manageable but needs active attention. Typical indicators are: summary schedule health is Yellow or mixed; 10-25% of active tasks are Red or Yellow; some important milestones are late, at risk, or dependent on external inputs; blockers exist but have owners or near-term resolution dates; several tasks are on hold; or sentiment suggests recurring friction such as pending mappings, delayed workshops, missing data, or open client decisions. Amber means the project can recover without executive escalation if actions are taken within the next reporting cycle.

### Red

A project is Red when committed outcomes, timeline, or stakeholder confidence are materially at risk. Typical indicators are: summary schedule health is Red; more than 25% of active tasks are Red or Yellow; critical path or near-term milestones are late; the project is marked high risk with unresolved blockers; completion is materially behind expected progress for the elapsed schedule; comments indicate repeated delays, missing client inputs, unresolved integrations, or blocked decisions; or there are enough missing/unparseable fields that leadership cannot trust the plan without PM follow-up.

## Signal Weighting

The agent uses a weighted risk score, then converts it to RAG:

- Schedule health and slippage: 35%. Uses workbook summary health, task-level Red/Yellow counts, overdue open tasks, and baseline variance when available.
- Milestone health: 25%. Looks at phase/milestone rows, critical tasks, near-term due dates, blocked or on-hold milestone work, and incomplete tasks due in the next 14 days.
- Execution progress: 15%. Compares percent complete, completed/in-progress/not-started mix, and elapsed project duration.
- Blockers and comments: 15%. Detects blocker language such as pending, delayed, impacted, dependency, waiting, incomplete, risk, issue, and client action needed.
- Budget burn: 10%. Applied only when budget data exists. For these samples, this signal is excluded from scoring and reported as unavailable.

Suggested thresholds: Green = score below 35; Amber = 35-64; Red = 65 or above. A hard override sets the project to Red if the workbook's summary schedule health is Red and the project is also marked high risk, or if a critical milestone is overdue with no clear recovery comment.

The implementation uses an additive point-based version of these weights so each risk signal remains auditable in the generated report. The point values are grouped by the same categories above rather than delegated to an LLM, which keeps the RAG decision deterministic and explainable.

## Output Standard

Each weekly output should include the RAG color, confidence level, top three reasons, key blockers, upcoming milestone risks, missing data, and recommended next actions. The explanation should be written for a VP or client sponsor: concise, specific, and action-oriented.
