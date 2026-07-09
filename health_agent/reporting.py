"""Report rendering and persistence for project health outputs."""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .models import HealthReport
from .utils import escape_pipe, format_pct, unique_nonblank

LOGGER = logging.getLogger("project_health_agent")


def render_markdown(report: HealthReport) -> str:
    """Render a weekly project health report as Markdown."""
    metrics = report.metrics
    lines = [
        f"# Weekly Project Health Report - {report.project_name}",
        "",
        f"- **RAG Status:** {report.rag}",
        f"- **Risk Score:** {report.score}/100",
        f"- **Confidence:** {report.confidence}",
        f"- **Project Manager:** {report.project_manager}",
        f"- **Reporting Date:** {report.reporting_date}",
        f"- **Project Stage:** {metrics.get('project_stage') or 'Unknown'}",
        f"- **Percent Complete:** {format_pct(metrics.get('percent_complete'))}",
        "",
        "## Plain-English Reasoning",
    ]
    lines.extend(f"- {reason}" for reason in report.top_reasons)
    lines.extend(render_metrics(metrics))
    lines.extend(render_list_section("Blockers / Watch Items", report.blockers, "None detected in available data."))
    lines.extend(render_list_section("Upcoming Risks", report.upcoming_risks, "No near-term risky tasks detected."))
    lines.extend(render_list_section("Recommendations", report.recommendations, "No recommendations generated."))
    lines.extend(render_list_section("Data Quality Notes", unique_nonblank(report.missing_data + report.confidence_notes), "No data quality issues detected."))
    lines.extend(render_evidence(report))
    return "\n".join(lines)


def render_metrics(metrics: dict) -> list[str]:
    """Render the key metrics section for Markdown output."""
    return [
        "",
        "## Key Metrics",
        f"- Active tasks: {metrics['active_tasks']} of {metrics['total_tasks']}",
        f"- Red/Yellow active tasks: {metrics['red_yellow_active_tasks']} ({format_pct(metrics['red_yellow_active_pct'])})",
        f"- Overdue open tasks: {metrics['overdue_open_tasks']}",
        f"- Critical or zero-float overdue tasks: {metrics['critical_overdue_tasks']}",
        f"- On-hold tasks: {metrics['on_hold_tasks']}",
        f"- PM comments with blocker language: {metrics['blocker_comment_count']} of {metrics['comment_count']}",
    ]


def render_list_section(title: str, items: list[str], empty_text: str) -> list[str]:
    """Render a titled Markdown bullet-list section."""
    lines = ["", f"## {title}"]
    lines.extend(f"- {item}" for item in items) if items else lines.append(f"- {empty_text}")
    return lines


def render_evidence(report: HealthReport) -> list[str]:
    """Render task evidence rows as a Markdown table."""
    lines = ["", "## Evidence Rows"]
    if not report.evidence:
        return lines + ["- No evidence rows available.", ""]
    lines.extend(["| Row | Task | Status | Health | End Date | % Complete | Critical | Overdue |", "|---:|---|---|---|---|---:|---|---|"])
    for item in report.evidence:
        lines.append(
            "| {row} | {task} | {status} | {health} | {end} | {pct} | {critical} | {overdue} |".format(
                row=item["row"],
                task=escape_pipe(item["task"]),
                status=item["status"],
                health=item["schedule_health"],
                end=item["end_date"],
                pct=format_pct(item["percent_complete"]),
                critical="Yes" if item["critical"] else "No",
                overdue="Yes" if item["overdue"] else "No",
            )
        )
    return lines + [""]


def save_reports(reports: list[HealthReport], output_dir: Path, run_date: str) -> None:
    """Write project reports, portfolio summary, and run manifest."""
    output_dir.mkdir(parents=True, exist_ok=True)
    report_files: list[str] = []
    for report in reports:
        safe_name = safe_filename(report.project_name)
        json_path = output_dir / f"{safe_name}_weekly_health.json"
        md_path = output_dir / f"{safe_name}_weekly_health.md"
        json_path.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
        md_path.write_text(render_markdown(report), encoding="utf-8")
        report_files.extend([str(json_path), str(md_path)])
        LOGGER.info("Wrote report files: %s, %s", json_path, md_path)

    portfolio_path = output_dir / "portfolio_weekly_summary.md"
    portfolio_path.write_text(render_portfolio_summary(reports), encoding="utf-8")
    report_files.append(str(portfolio_path))
    write_manifest(output_dir / "run_manifest.json", reports, report_files, run_date)
    LOGGER.info("Wrote portfolio summary and manifest: %s, %s", portfolio_path, output_dir / "run_manifest.json")


def safe_filename(value: str) -> str:
    """Convert a project name into a filesystem-safe filename stem."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "project"


def write_manifest(path: Path, reports: list[HealthReport], report_files: list[str], run_date: str) -> None:
    """Write machine-readable metadata for a weekly run."""
    manifest = {
        "run_date": run_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "project_count": len(reports),
        "reports": [
            {
                "project_name": report.project_name,
                "rag": report.rag,
                "score": report.score,
                "confidence": report.confidence,
                "source_file": report.source_file,
            }
            for report in reports
        ],
        "files": report_files,
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def render_portfolio_summary(reports: list[HealthReport]) -> str:
    """Render a concise cross-project weekly portfolio summary."""
    counts = Counter(report.rag for report in reports)
    lines = [
        "# Weekly Portfolio Health Summary",
        "",
        f"- Projects analyzed: {len(reports)}",
        f"- Red: {counts.get('Red', 0)}",
        f"- Amber: {counts.get('Amber', 0)}",
        f"- Green: {counts.get('Green', 0)}",
        "",
        "| Project | RAG | Score | Confidence | Primary Reason |",
        "|---|---|---:|---|---|",
    ]
    for report in reports:
        reason = report.top_reasons[0] if report.top_reasons else "No material risk reason generated."
        lines.append(f"| {escape_pipe(report.project_name)} | {report.rag} | {report.score} | {report.confidence} | {escape_pipe(reason)} |")
    lines.extend(["", "## Portfolio Themes"])
    lines.extend(portfolio_themes(reports))
    return "\n".join(lines) + "\n"


def portfolio_themes(reports: list[HealthReport]) -> list[str]:
    """Generate cross-project portfolio themes from weekly reports."""
    themes = []
    if any(report.metrics["blocker_comment_count"] for report in reports):
        themes.append("- Several risks are dependency-driven, especially where comments mention pending data, mappings, or impacted workshops.")
    if any(report.metrics["near_term_risky_tasks"] for report in reports):
        themes.append("- Near-term milestones need active review because multiple tasks due soon are incomplete or marked Red/Yellow.")
    if all("Budget fields were not present; budget burn is not scored." in report.missing_data for report in reports):
        themes.append("- Budget health is a portfolio reporting gap across the sample files.")
    return themes or ["- No strong cross-project risk pattern was detected beyond individual project schedule signals."]

