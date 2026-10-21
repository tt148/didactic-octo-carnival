"""Configurable title and location eligibility checks."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal

from remote_job_tracker.models import Job

GENERIC_SUPPORT_TERMS = ("support engineer", "support specialist", "support technician")
TECHNICAL_CONTEXT_TERMS = (
    "application",
    "cloud",
    "desktop",
    "devops",
    "hardware",
    "help desk",
    "helpdesk",
    "it",
    "linux",
    "network",
    "saas",
    "service desk",
    "software",
    "system",
    "technical",
    "tech support",
    "windows",
)
LOCATION_CUES_BEFORE = {"based", "located", "live", "reside"}
LOCATION_CUES_AFTER = {
    "based",
    "citizen",
    "employee",
    "only",
    "remote",
    "resident",
    "residents",
    "restricted",
}
UNKNOWN_LOCATIONS = {"", "anywhere", "n a", "not specified", "remote", "unknown"}
LocationAssessmentStatus = Literal["allowed", "unknown", "restricted"]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _contains_phrase(text: str, phrase: str) -> bool:
    text_tokens = _tokens(text)
    phrase_tokens = _tokens(phrase)
    size = len(phrase_tokens)
    return bool(size) and any(
        text_tokens[index : index + size] == phrase_tokens
        for index in range(len(text_tokens) - size + 1)
    )


def title_matches(job: Job, config: Mapping[str, object]) -> bool:
    title = job.title.casefold()
    include = config.get("title_include", [])
    exclude = config.get("title_exclude", [])
    if not isinstance(include, list) or not isinstance(exclude, list):
        raise ValueError("Title include and exclude config values must be lists.")
    if any(str(term).casefold() in title for term in exclude):
        return False
    if not any(str(term).casefold() in title for term in include):
        return False
    generic_support = any(term in title for term in GENERIC_SUPPORT_TERMS)
    if generic_support and not any(term in title for term in TECHNICAL_CONTEXT_TERMS):
        return False
    return True


def _text_has_location_restriction(
    title: str, description: str, denied_terms: list[str]
) -> str | None:
    tokens = _tokens(f"{title} {description}")
    for term in denied_terms:
        phrase_tokens = _tokens(term)
        size = len(phrase_tokens)
        for index in range(len(tokens) - size + 1):
            if tokens[index : index + size] != phrase_tokens:
                continue
            before = tokens[max(0, index - 6) : index]
            after = tokens[index + size : index + size + 4]
            if LOCATION_CUES_BEFORE.intersection(before) or LOCATION_CUES_AFTER.intersection(
                after
            ):
                return term
            if len(before) >= 2 and before[-2:] == ["based", "in"]:
                return term
            if len(before) >= 2 and before[-2:] == ["reside", "in"]:
                return term
            if len(before) >= 2 and before[-2:] == ["located", "in"]:
                return term
    return None


def assess_location(
    job: Job, config: Mapping[str, object]
) -> tuple[LocationAssessmentStatus, str]:
    allowed = config.get("location_allow", [])
    denied = config.get("location_deny", [])
    if not isinstance(allowed, list) or not isinstance(denied, list):
        raise ValueError("Location allow and deny config values must be lists.")
    denied_terms = [str(term) for term in denied]
    restricted = _text_has_location_restriction(
        job.title, job.description, denied_terms
    )
    if restricted:
        return "restricted", f"Explicit {restricted} restriction in title or description."
    if any(_contains_phrase(job.location, term) for term in denied_terms):
        return "restricted", "Location is explicitly restricted by configuration."
    normalized_location = " ".join(_tokens(job.location))
    if normalized_location in UNKNOWN_LOCATIONS:
        return "unknown", "Location is missing or too general to confirm eligibility."
    if any(_contains_phrase(job.location, str(term)) for term in allowed):
        return "allowed", "Location matches an allowed region."
    return "unknown", "Location does not confirm eligibility for Nigeria."


def keep_job(job: Job, config: Mapping[str, object]) -> bool:
    if not title_matches(job, config):
        return False
    status, reason = assess_location(job, config)
    if status == "restricted":
        return False
    job.location_status = status
    job.location_reason = reason
    return True
