"""Utility helpers for parsing workbook values and formatting output."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any


def normalize(value: Any) -> str:
    """Return a trimmed string for any workbook cell value."""
    if value is None:
        return ""
    return str(value).strip()


def parse_date(value: Any) -> date | None:
    """Parse common Excel/openpyxl date values into a date."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalize(value)
    if not text or text.startswith("#"):
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%y %I:%M %p", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_percent(value: Any) -> float | None:
    """Parse a percentage cell as a decimal between 0 and 1 when possible."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = normalize(value).replace("%", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return number / 100 if number > 1 else number


def parse_variance_days(value: Any) -> float | None:
    """Parse schedule variance values such as '-32d' into absolute days."""
    text = normalize(value).lower()
    if not text or text.startswith("#"):
        return None
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*d", text)
    if match:
        return abs(float(match.group(1)))
    try:
        return abs(float(text))
    except ValueError:
        return None


def is_true(value: Any) -> bool:
    """Interpret common truthy workbook values."""
    if isinstance(value, bool):
        return value
    return normalize(value).lower() in {"true", "yes", "y", "1"}


def is_zero_float(value: Any) -> bool:
    """Return whether total float is effectively zero."""
    if value is None or value == "":
        return False
    try:
        return math.isclose(float(value), 0.0)
    except (TypeError, ValueError):
        return False


def calculate_ratio(numerator: int, denominator: int) -> float | None:
    """Safely calculate a ratio or return None for empty denominators."""
    if denominator <= 0:
        return None
    return numerator / denominator


def format_pct(value: Any) -> str:
    """Format a decimal percentage for human-readable reports."""
    if value is None:
        return "n/a"
    try:
        return f"{float(value) * 100:.0f}%"
    except (TypeError, ValueError):
        return "n/a"


def escape_pipe(text: str) -> str:
    """Escape pipe characters for Markdown table cells."""
    return text.replace("|", "\\|")


def unique_nonblank(items: list[str]) -> list[str]:
    """Return unique non-empty strings while preserving input order."""
    seen = set()
    unique = []
    for item in items:
        cleaned = normalize(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            unique.append(cleaned)
    return unique
