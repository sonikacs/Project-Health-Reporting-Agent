"""Command-line entrypoint for weekly project health reporting."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from .llm_narrative import enhance_reports_with_llm
from .reporting import save_reports
from .scoring import score_project

LOGGER = logging.getLogger("project_health_agent")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the weekly agent."""
    parser = argparse.ArgumentParser(description="Generate project health reports from Excel project plans.")
    parser.add_argument("files", nargs="+", type=Path, help="Project plan .xlsx files")
    parser.add_argument("--output-dir", type=Path, default=Path("outputs") / "weekly", help="Directory for generated reports")
    parser.add_argument("--run-date", default=date.today().isoformat(), help="Run date used in output metadata, format YYYY-MM-DD")
    parser.add_argument("--log-dir", type=Path, default=Path("logs"), help="Directory for run logs")
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first workbook error")
    parser.add_argument("--disable-llm", action="store_true", help="Disable LLM narrative generation and use deterministic template text")
    parser.add_argument("--llm-provider", default="gemini", choices=("gemini", "openai"), help="LLM provider used for narrative generation")
    parser.add_argument("--llm-model", default="gemini-3.5-flash", help="LLM model used for narrative generation")
    return parser.parse_args()


def setup_logging(log_dir: Path, run_date: str) -> Path:
    """Configure console and file logging for a weekly run."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"weekly_agent_{run_date}.log"
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    root.addHandler(console_handler)
    return log_path


def run(
    files: list[Path],
    output_dir: Path,
    run_date: str,
    fail_fast: bool,
    use_llm: bool,
    llm_provider: str,
    llm_model: str,
) -> tuple[list, list[dict[str, str]]]:
    """Score workbooks and return successful reports plus failures."""
    reports = []
    failures = []
    for path in files:
        try:
            reports.append(score_project(path))
        except Exception as exc:
            LOGGER.exception("Failed to process workbook: %s", path)
            failures.append({"file": str(path), "error": str(exc)})
            if fail_fast:
                raise
    if not reports:
        LOGGER.error("No reports generated. Failures: %s", failures)
        raise SystemExit(1)
    enhance_reports_with_llm(reports, use_llm, llm_provider, llm_model)
    save_reports(reports, output_dir, run_date)
    return reports, failures


def main() -> None:
    """Run the weekly project health reporting workflow."""
    args = parse_args()
    log_path = setup_logging(args.log_dir, args.run_date)
    LOGGER.info("Starting weekly project health run date=%s output_dir=%s", args.run_date, args.output_dir)
    reports, failures = run(
        args.files,
        args.output_dir,
        args.run_date,
        args.fail_fast,
        not args.disable_llm,
        args.llm_provider,
        args.llm_model,
    )
    for report in reports:
        LOGGER.info("Result rag=%s score=%s project='%s'", report.rag, report.score, report.project_name)
    if failures:
        LOGGER.warning("Completed with %s failed workbook(s). See log: %s", len(failures), log_path)
    LOGGER.info("Wrote %s report(s) to %s", len(reports), args.output_dir)
    LOGGER.info("Log file: %s", log_path)
