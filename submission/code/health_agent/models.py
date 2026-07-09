"""Shared data models for project health reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HealthReport:
    """Structured output for a single project health assessment."""

    source_file: str
    project_name: str
    project_manager: str
    reporting_date: str
    rag: str
    score: int
    confidence: str
    confidence_notes: list[str]
    summary: dict[str, Any]
    metrics: dict[str, Any]
    top_reasons: list[str]
    blockers: list[str]
    upcoming_risks: list[str]
    missing_data: list[str]
    recommendations: list[str]
    evidence: list[dict[str, Any]] = field(default_factory=list)

