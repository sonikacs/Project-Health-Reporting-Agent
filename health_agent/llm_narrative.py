"""LLM narrative generation for weekly project health reports."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from .models import HealthReport

LOGGER = logging.getLogger("project_health_agent")
GEMINI_INTERACTIONS_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
MAX_LLM_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2
TRANSIENT_HTTP_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


def enhance_reports_with_llm(reports: list[HealthReport], enabled: bool, provider: str, model: str) -> None:
    """Rewrite report reasoning and recommendations with an LLM when enabled."""
    if not enabled:
        LOGGER.info("LLM narrative generation explicitly disabled; using deterministic template text.")
        return

    provider = provider.lower()
    api_key = get_api_key(provider)
    if not api_key:
        LOGGER.warning("%s API key is not set; falling back to deterministic template narrative.", provider.upper())
        return

    for report in reports:
        try:
            enhanced = generate_project_narrative(report, api_key, provider, model)
        except Exception as exc:
            LOGGER.warning(
                "LLM narrative generation failed for project='%s'; using deterministic fallback narrative. Reason: %s",
                report.project_name,
                exc,
            )
            LOGGER.debug("LLM narrative generation traceback for project='%s'", report.project_name, exc_info=True)
            continue
        apply_llm_narrative(report, enhanced)
        LOGGER.info("Applied LLM narrative for project='%s' provider=%s model=%s", report.project_name, provider, model)


def get_api_key(provider: str) -> str | None:
    """Return the API key environment variable for the selected provider."""
    if provider == "gemini":
        return os.getenv("GEMINI_API_KEY")
    if provider == "openai":
        return os.getenv("OPENAI_API_KEY")
    raise ValueError(f"Unsupported LLM provider: {provider}")


def generate_project_narrative(report: HealthReport, api_key: str, provider: str, model: str) -> dict[str, Any]:
    """Call the configured LLM provider to create executive-ready report narrative."""
    if provider == "gemini":
        return generate_project_narrative_with_gemini(report, api_key, model)
    if provider == "openai":
        return generate_project_narrative_with_openai(report, api_key, model)
    raise ValueError(f"Unsupported LLM provider: {provider}")


def generate_project_narrative_with_gemini(report: HealthReport, api_key: str, model: str) -> dict[str, Any]:
    """Call the Gemini Interactions API to create executive-ready report narrative."""
    payload = {
        "model": model,
        "input": build_prompt(report),
        "system_instruction": "Return only strict JSON. Do not include markdown fences.",
    }
    response_payload = post_json_with_retries(
        url=GEMINI_INTERACTIONS_URL,
        payload=payload,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        provider="Gemini",
        model=model,
    )
    return parse_model_json(response_payload)


def generate_project_narrative_with_openai(report: HealthReport, api_key: str, model: str) -> dict[str, Any]:
    """Call the OpenAI Responses API to create executive-ready report narrative."""
    payload = {
        "model": model,
        "input": build_prompt(report),
    }
    response_payload = post_json_with_retries(
        url=OPENAI_RESPONSES_URL,
        payload=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        provider="OpenAI",
        model=model,
    )
    return parse_model_json(response_payload)


def post_json_with_retries(url: str, payload: dict[str, Any], headers: dict[str, str], provider: str, model: str) -> dict[str, Any]:
    """POST JSON to an LLM API with bounded retries for transient provider errors."""
    for attempt in range(1, MAX_LLM_ATTEMPTS + 1):
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if should_retry_http_status(exc.code) and attempt < MAX_LLM_ATTEMPTS:
                log_retry(provider, model, attempt, f"HTTP {exc.code}: {truncate_text(body)}")
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue
            raise RuntimeError(f"{provider} API request failed with HTTP {exc.code}: {truncate_text(body)}") from exc
        except urllib.error.URLError as exc:
            if attempt < MAX_LLM_ATTEMPTS:
                log_retry(provider, model, attempt, str(exc.reason))
                time.sleep(RETRY_DELAY_SECONDS * attempt)
                continue
            raise RuntimeError(f"{provider} API request failed: {exc.reason}") from exc
    raise RuntimeError(f"{provider} API request failed after {MAX_LLM_ATTEMPTS} attempts.")


def should_retry_http_status(status_code: int) -> bool:
    """Return whether an HTTP status code is usually safe to retry."""
    return status_code in TRANSIENT_HTTP_STATUS_CODES


def log_retry(provider: str, model: str, attempt: int, reason: str) -> None:
    """Log a concise retry message for a transient LLM provider failure."""
    LOGGER.warning(
        "%s API transient failure for model=%s attempt=%s/%s; retrying. Reason: %s",
        provider,
        model,
        attempt,
        MAX_LLM_ATTEMPTS,
        reason,
    )


def truncate_text(value: str, limit: int = 500) -> str:
    """Trim long provider error bodies before writing them to logs."""
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit]}..."


def build_prompt(report: HealthReport) -> str:
    """Build a constrained prompt that preserves deterministic RAG decisions."""
    report_data = asdict(report)
    return (
        "You are assisting a Professional Services project health reporting agent.\n"
        "Do not change the RAG status, score, metrics, or evidence. The deterministic rule engine is authoritative.\n"
        "Rewrite only the narrative fields so they are concise, plain-English, and executive-ready.\n"
        "Return strict JSON with exactly these keys: top_reasons, recommendations.\n"
        "top_reasons must be an array of 3 to 5 strings. recommendations must be an array of 3 to 5 strings.\n\n"
        f"Project report JSON:\n{json.dumps(report_data, default=str)}"
    )


def parse_model_json(response_payload: dict[str, Any]) -> dict[str, Any]:
    """Extract and parse JSON text from a Gemini or OpenAI response payload."""
    text = response_payload.get("output_text") or collect_response_text(response_payload)
    if not text:
        raise ValueError("LLM response did not contain output text.")
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response JSON must be an object.")
    return parsed


def collect_response_text(response_payload: dict[str, Any]) -> str:
    """Collect text content from known LLM response structures."""
    if isinstance(response_payload.get("output_text"), str):
        return response_payload["output_text"]

    chunks: list[str] = []
    for item in response_payload.get("output", []):
        for content in item.get("content", []):
            if "text" in content:
                chunks.append(content["text"])
    for step in response_payload.get("steps", []):
        for content in step.get("content", []):
            if isinstance(content, dict) and "text" in content:
                chunks.append(content["text"])
    return "\n".join(chunks)


def apply_llm_narrative(report: HealthReport, narrative: dict[str, Any]) -> None:
    """Apply validated LLM narrative fields to a report in place."""
    top_reasons = narrative.get("top_reasons")
    recommendations = narrative.get("recommendations")
    if is_string_list(top_reasons):
        report.top_reasons = top_reasons[:5]
    if is_string_list(recommendations):
        report.recommendations = recommendations[:5]


def is_string_list(value: Any) -> bool:
    """Return whether a value is a non-empty list of strings."""
    return isinstance(value, list) and bool(value) and all(isinstance(item, str) for item in value)
