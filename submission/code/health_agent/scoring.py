"""Deterministic RAG scoring and project health analysis."""

from __future__ import annotations

import logging
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .models import HealthReport
from .utils import (
    format_pct,
    is_true,
    is_zero_float,
    normalize,
    parse_date,
    parse_percent,
    parse_variance_days,
    calculate_ratio,
    unique_nonblank,
)
from .workbook_parser import load_workbook_data

LOGGER = logging.getLogger("project_health_agent")

BLOCKER_TERMS = (
    "blocked",
    "blocker",
    "delay",
    "delayed",
    "impacted",
    "pending",
    "waiting",
    "dependency",
    "dependencies",
    "issue",
    "risk",
    "incomplete",
    "remain",
    "missing",
    "not received",
    "on hold",
)
COMPLETE_STATUSES = {"completed", "complete", "done", "closed"}
OPEN_STATUSES = {"not started", "in progress", "on hold", "open"}
NA_STATUSES = {"not applicable", "n/a", "na"}


def score_project(path: Path) -> HealthReport:
    """Generate a complete health report for one project workbook."""
    if not path.exists():
        raise FileNotFoundError(f"Input workbook not found: {path}")
    if path.suffix.lower() != ".xlsx":
        raise ValueError(f"Input must be an .xlsx workbook: {path}")

    summary, tasks, comments, warnings = load_workbook_data(path)
    reporting_date = parse_date(summary.get("Today's Date")) or date.today()
    metrics = calculate_metrics(summary, tasks, comments, reporting_date)
    score, reasons = calculate_score(metrics)
    rag = score_to_rag(score)
    rag, reasons = apply_overrides(rag, metrics, reasons)
    confidence, confidence_notes = calculate_confidence(warnings, summary, metrics)

    report = HealthReport(
        source_file=str(path),
        project_name=infer_project_name(path, summary, tasks),
        project_manager=normalize(summary.get("Project Manager")) or first_nonblank(tasks, "Project Manager") or "Unknown",
        reporting_date=reporting_date.isoformat(),
        rag=rag,
        score=score,
        confidence=confidence,
        confidence_notes=confidence_notes,
        summary=clean_summary(summary),
        metrics=metrics,
        top_reasons=prioritize_reasons(reasons)[:5],
        blockers=identify_blockers(tasks, comments),
        upcoming_risks=identify_upcoming_risks(tasks, reporting_date),
        missing_data=warnings + metric_missing_data(summary),
        recommendations=build_recommendations(rag, metrics),
        evidence=select_evidence(tasks, reporting_date),
    )
    LOGGER.info("Scored project='%s' rag=%s score=%s confidence=%s", report.project_name, report.rag, report.score, report.confidence)
    return report


def calculate_metrics(summary: dict[str, Any], tasks: list[dict[str, Any]], comments: list[dict[str, Any]], reporting_date: date) -> dict[str, Any]:
    """Calculate schedule, milestone, blocker, and progress metrics."""
    active_tasks = [task for task in tasks if normalize(task.get("Status")).lower() not in COMPLETE_STATUSES | NA_STATUSES]
    red_yellow_active = [task for task in active_tasks if normalize(task.get("Schedule Health")).lower() in {"red", "yellow", "amber"}]
    overdue_open = [task for task in active_tasks if is_overdue(task, reporting_date)]
    critical_overdue = [task for task in overdue_open if is_true(task.get("Critical ?")) or is_zero_float(task.get("Total Float"))]
    on_hold = [task for task in active_tasks if normalize(task.get("Status")).lower() == "on hold" or is_true(task.get("On Hold?"))]
    near_term_open = [task for task in active_tasks if is_within_days(task.get("End Date"), reporting_date, 14)]
    near_term_bad = [task for task in near_term_open if is_risky_near_term_task(task)]
    variances = [days for task in tasks if (days := parse_variance_days(task.get("Variance"))) is not None]
    progress = parse_percent(summary.get("% Complete"))
    elapsed_ratio = calculate_elapsed_ratio(summary, reporting_date)

    return {
        "total_tasks": len(tasks),
        "active_tasks": len(active_tasks),
        "status_counts": dict(Counter(normalize(task.get("Status")).title() or "Blank" for task in tasks)),
        "schedule_health_counts": dict(Counter(normalize(task.get("Schedule Health")).title() or "Blank" for task in tasks)),
        "red_yellow_active_tasks": len(red_yellow_active),
        "red_yellow_active_pct": calculate_ratio(len(red_yellow_active), len(active_tasks)),
        "overdue_open_tasks": len(overdue_open),
        "critical_overdue_tasks": len(critical_overdue),
        "on_hold_tasks": len(on_hold),
        "at_risk_flagged_tasks": sum(1 for task in tasks if is_true(task.get("At Risk?"))),
        "near_term_open_tasks": len(near_term_open),
        "near_term_risky_tasks": len(near_term_bad),
        "blocker_comment_count": count_blocker_comments(comments),
        "comment_count": len(comments),
        "comment_terms_detected": sorted({term for term in BLOCKER_TERMS if term in " ".join(c["comment"] for c in comments).lower()}),
        "summary_schedule_health": normalize(summary.get("Schedule Health")).title(),
        "summary_at_risk": normalize(summary.get("At Risk")).title(),
        "project_stage": normalize(summary.get("Project Stage")),
        "percent_complete": progress,
        "elapsed_schedule_pct": elapsed_ratio,
        "progress_gap_pct": max(0.0, elapsed_ratio - progress) if progress is not None and elapsed_ratio is not None else None,
        "max_variance_days": max(variances) if variances else None,
        "avg_variance_days": sum(variances) / len(variances) if variances else None,
        "variance_count": len(variances),
    }


def calculate_score(metrics: dict[str, Any]) -> tuple[int, list[str]]:
    """Convert calculated metrics into a deterministic risk score."""
    score = 0
    reasons: list[str] = []
    score += add_summary_health_score(metrics, reasons)
    score += add_task_health_score(metrics, reasons)
    score += add_milestone_score(metrics, reasons)
    score += add_risk_signal_score(metrics, reasons)
    return min(100, round(score)), reasons


def add_summary_health_score(metrics: dict[str, Any], reasons: list[str]) -> int:
    """Score the workbook-level schedule health signal."""
    health = metrics["summary_schedule_health"]
    if health == "Red":
        reasons.append("The workbook summary marks overall schedule health as Red.")
        return 25
    if health in {"Yellow", "Amber"}:
        reasons.append("The workbook summary marks overall schedule health as Amber/Yellow.")
        return 15
    if health == "Green":
        reasons.append("The workbook summary marks overall schedule health as Green.")
    return 0


def add_task_health_score(metrics: dict[str, Any], reasons: list[str]) -> int:
    """Score active Red/Yellow task concentration."""
    ratio = metrics["red_yellow_active_pct"] or 0
    if ratio >= 0.25:
        reasons.append(f"{format_pct(ratio)} of active tasks are Red/Yellow.")
        return 20
    if ratio >= 0.10:
        reasons.append(f"{format_pct(ratio)} of active tasks are Red/Yellow.")
        return 12
    if ratio > 0:
        reasons.append(f"A small share of active tasks are Red/Yellow ({format_pct(ratio)}).")
        return 5
    return 0


def add_milestone_score(metrics: dict[str, Any], reasons: list[str]) -> int:
    """Score overdue, critical, near-term, and on-hold work."""
    score = 0
    if metrics["critical_overdue_tasks"]:
        score += 20
        reasons.append(f"{metrics['critical_overdue_tasks']} critical or zero-float open task(s) are overdue.")
    elif metrics["overdue_open_tasks"]:
        score += 12
        reasons.append(f"{metrics['overdue_open_tasks']} open task(s) are past their planned end date.")
    if metrics["near_term_risky_tasks"]:
        score += min(15, 5 + metrics["near_term_risky_tasks"])
        reasons.append(f"{metrics['near_term_risky_tasks']} near-term task(s) due in the next 14 days look risky.")
    if metrics["on_hold_tasks"]:
        score += min(10, 4 + metrics["on_hold_tasks"] * 2)
        reasons.append(f"{metrics['on_hold_tasks']} active task(s) are on hold.")
    return score


def add_risk_signal_score(metrics: dict[str, Any], reasons: list[str]) -> int:
    """Score at-risk flags, progress gaps, blocker comments, and variance."""
    score = 0
    if metrics["at_risk_flagged_tasks"]:
        score += min(10, metrics["at_risk_flagged_tasks"] * 3)
        reasons.append(f"{metrics['at_risk_flagged_tasks']} task(s) are explicitly flagged at risk.")
    if metrics["summary_at_risk"] == "High":
        score += 8
        reasons.append("The project summary risk level is High.")
    elif metrics["summary_at_risk"] == "Medium":
        score += 4
        reasons.append("The project summary risk level is Medium.")
    if (gap := metrics["progress_gap_pct"]) is not None and gap >= 0.10:
        score += 15 if gap >= 0.20 else 8
        reasons.append(f"Completion trails elapsed schedule by about {format_pct(gap)}.")
    if metrics["blocker_comment_count"] >= 3:
        score += 10
        reasons.append(f"{metrics['blocker_comment_count']} comments contain blocker or dependency language.")
    elif metrics["blocker_comment_count"]:
        score += 5
        reasons.append("Recent comments include blocker or dependency language.")
    if metrics["max_variance_days"] and metrics["max_variance_days"] >= 20:
        score += 8
        reasons.append(f"Task variance reaches {metrics['max_variance_days']:.0f} day(s).")
    return score


def apply_overrides(rag: str, metrics: dict[str, Any], reasons: list[str]) -> tuple[str, list[str]]:
    """Apply hard RAG overrides for severe project-health conditions."""
    if metrics["summary_schedule_health"] == "Red" and metrics["summary_at_risk"] == "High":
        return "Red", reasons
    if metrics["critical_overdue_tasks"] >= 3:
        if rag != "Red":
            reasons.insert(0, "Override: multiple critical or zero-float tasks are overdue.")
        return "Red", reasons
    return rag, reasons


def prioritize_reasons(reasons: list[str]) -> list[str]:
    """Sort reasoning bullets so executive-critical signals appear first."""
    priority_terms = ("Override:", "summary marks overall schedule health", "summary risk level is High", "critical or zero-float", "past their planned end date", "blocker or dependency", "near-term")
    ranked = []
    for index, reason in enumerate(reasons):
        rank = next((i for i, term in enumerate(priority_terms) if term in reason), len(priority_terms))
        if "summary marks overall schedule health as Green" in reason:
            rank = len(priority_terms) + 1
        ranked.append((rank, index, reason))
    return [reason for _, _, reason in sorted(ranked)]


def score_to_rag(score: int) -> str:
    """Map a numeric risk score to Green, Amber, or Red."""
    if score >= 65:
        return "Red"
    if score >= 35:
        return "Amber"
    return "Green"


def calculate_confidence(warnings: list[str], summary: dict[str, Any], metrics: dict[str, Any]) -> tuple[str, list[str]]:
    """Assess confidence based on readable data and missing signals."""
    notes = list(warnings)
    if metrics["comment_count"] == 0:
        notes.append("No PM comments were available, so blocker and sentiment assessment is limited.")
    if not summary:
        notes.append("Summary sheet was unavailable; scoring relies on task-level data.")
    if metrics["percent_complete"] is None:
        notes.append("Summary percent complete was unavailable or unparseable.")
    if len(notes) >= 4:
        return "Medium", notes
    if notes:
        return "Medium-High", notes
    return "High", ["Core schedule, status, and summary fields were readable."]


def identify_blockers(tasks: list[dict[str, Any]], comments: list[dict[str, Any]]) -> list[str]:
    """Extract blocker and watch-item text from comments and task health."""
    blockers = [f"{c['row_ref']}: {c['comment']}" if c["row_ref"] else c["comment"] for c in comments if has_blocker_language(c["comment"])]
    for task in tasks:
        status = normalize(task.get("Status")).lower()
        health = normalize(task.get("Schedule Health")).title()
        if status == "on hold" or is_true(task.get("On Hold?")):
            blockers.append(f"On hold: {normalize(task.get('Task Name'))}")
        elif health == "Red" and status in OPEN_STATUSES:
            blockers.append(f"Red active task: {normalize(task.get('Task Name'))}")
    return unique_nonblank(blockers)[:8]


def identify_upcoming_risks(tasks: list[dict[str, Any]], reporting_date: date) -> list[str]:
    """Find risky open tasks due within the next three weeks."""
    risks: list[tuple[date, str]] = []
    for task in tasks:
        if normalize(task.get("Status")).lower() in COMPLETE_STATUSES | NA_STATUSES:
            continue
        end = parse_date(task.get("End Date"))
        if end and reporting_date <= end <= reporting_date + timedelta(days=21) and is_risky_near_term_task(task):
            health = normalize(task.get("Schedule Health")).title()
            complete = parse_percent(task.get("% Complete")) or 0.0
            risks.append((end, f"{end.isoformat()}: {normalize(task.get('Task Name'))} ({health or 'No health'}, {format_pct(complete)} complete)"))
    return [risk for _, risk in sorted(risks)[:8]]


def build_recommendations(rag: str, metrics: dict[str, Any]) -> list[str]:
    """Build action-oriented recommendations from RAG and risk metrics."""
    recommendations = ["Run an executive recovery review focused on overdue critical work, owners, and revised milestone dates." if rag == "Red" else "Review amber risks in the next PM cadence and confirm owners and dates for each dependency." if rag == "Amber" else "Continue weekly monitoring and keep milestone dates current."]
    if metrics["near_term_risky_tasks"]:
        recommendations.append("Create a 14-day action plan for near-term risky tasks.")
    if metrics["blocker_comment_count"]:
        recommendations.append("Convert blocker comments into explicit actions with client/Zycus ownership.")
    if metrics["on_hold_tasks"]:
        recommendations.append("Resolve or rebaseline on-hold work so the plan reflects executable scope.")
    recommendations.append("Add budget/burn data to improve commercial health reporting.")
    return unique_nonblank(recommendations)


def select_evidence(tasks: list[dict[str, Any]], reporting_date: date) -> list[dict[str, Any]]:
    """Select representative task rows that justify the health rating."""
    evidence = []
    for task in tasks:
        status = normalize(task.get("Status")).lower()
        health = normalize(task.get("Schedule Health")).title()
        end = parse_date(task.get("End Date"))
        overdue = bool(end and end < reporting_date and status not in COMPLETE_STATUSES | NA_STATUSES)
        if health in {"Red", "Yellow", "Amber"} or overdue or status == "on hold":
            evidence.append({"row": task.get("_row"), "task": normalize(task.get("Task Name")), "status": normalize(task.get("Status")), "schedule_health": health, "end_date": end.isoformat() if end else "", "percent_complete": parse_percent(task.get("% Complete")), "critical": bool(is_true(task.get("Critical ?")) or is_zero_float(task.get("Total Float"))), "overdue": overdue})
    evidence.sort(key=lambda item: (not item["overdue"], item["schedule_health"] != "Red", item["end_date"]))
    return evidence[:12]


def metric_missing_data(summary: dict[str, Any]) -> list[str]:
    """Describe unavailable data that limits scoring completeness."""
    missing = ["Budget fields were not present; budget burn is not scored."]
    if not summary.get("Target Start Date") or str(summary.get("Target Start Date")).startswith("#"):
        missing.append("Target start date is missing or unparseable.")
    if not summary.get("Target End Date") or str(summary.get("Target End Date")).startswith("#"):
        missing.append("Target end date is missing or unparseable.")
    return missing


def infer_project_name(path: Path, summary: dict[str, Any], tasks: list[dict[str, Any]]) -> str:
    """Infer the project name from summary fields, tasks, or filename."""
    return normalize(summary.get("Project Name")) or first_nonblank(tasks, "Task Name") or path.stem


def first_nonblank(tasks: list[dict[str, Any]], column: str) -> str:
    """Return the first non-empty value found in a task column."""
    for task in tasks:
        if value := normalize(task.get(column)):
            return value
    return ""


def clean_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Convert summary values to JSON-safe primitives."""
    return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in summary.items()}


def is_overdue(task: dict[str, Any], reporting_date: date) -> bool:
    """Return whether an open task is past its planned end date."""
    status = normalize(task.get("Status")).lower()
    end = parse_date(task.get("End Date"))
    return bool(end and end < reporting_date and status not in COMPLETE_STATUSES | NA_STATUSES)


def is_within_days(value: Any, reporting_date: date, days: int) -> bool:
    """Return whether a date value lands within a forward-looking window."""
    end = parse_date(value)
    return bool(end and reporting_date <= end <= reporting_date + timedelta(days=days))


def is_risky_near_term_task(task: dict[str, Any]) -> bool:
    """Return whether a near-term task appears risky or under-complete."""
    health = normalize(task.get("Schedule Health")).lower()
    complete = parse_percent(task.get("% Complete")) or 0
    return health in {"red", "yellow", "amber"} or complete < 0.75


def calculate_elapsed_ratio(summary: dict[str, Any], reporting_date: date) -> float | None:
    """Calculate elapsed project schedule as a percentage of duration."""
    start = parse_date(summary.get("Project Start Date"))
    end = parse_date(summary.get("Project End Date"))
    if not start or not end or end <= start:
        return None
    return min(1.0, max(0.0, (reporting_date - start).days / (end - start).days))


def count_blocker_comments(comments: list[dict[str, Any]]) -> int:
    """Count comments that contain blocker or dependency language."""
    return sum(1 for comment in comments if has_blocker_language(comment["comment"]))


def has_blocker_language(text: str) -> bool:
    """Return whether text contains any configured blocker terms."""
    lower = text.lower()
    return any(term in lower for term in BLOCKER_TERMS)
