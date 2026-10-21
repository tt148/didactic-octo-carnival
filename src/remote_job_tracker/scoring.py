"""Transparent profile matching and job fit scoring."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from remote_job_tracker.filters import assess_location
from remote_job_tracker.models import Job

DEFAULT_WEIGHTS: dict[str, int] = {
    "skills": 50,
    "role": 25,
    "location": 15,
    "seniority": 10,
    "unknown_location": 5,
    "senior_stretch_penalty": 4,
    "high_stretch_penalty": 7,
}


@dataclass(frozen=True, slots=True)
class FitScore:
    score: int
    reasons: tuple[str, ...]


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def _has_phrase(text: str, phrase: str) -> bool:
    text_tokens = _tokens(text)
    phrase_tokens = _tokens(phrase)
    size = len(phrase_tokens)
    return bool(size) and any(
        text_tokens[index : index + size] == phrase_tokens
        for index in range(len(text_tokens) - size + 1)
    )


def _required_list(mapping: Mapping[str, object], key: str) -> list[str]:
    value = mapping.get(key, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"Profile field {key!r} must be a list of strings.")
    return value


def score_job(job: Job, config: Mapping[str, object]) -> FitScore:
    """Return a 0-100 score with one reason for each scoring component."""
    profile = config.get("profile")
    if not isinstance(profile, Mapping):
        raise ValueError("Config must include a profile object for fit scoring.")
    skills = _required_list(profile, "skills")
    primary_roles = _required_list(profile, "primary_roles")
    secondary_roles = _required_list(profile, "secondary_roles")
    seniority_terms = _required_list(profile, "seniority_stretch_terms")
    high_stretch_terms = _required_list(profile, "high_stretch_terms")
    if not skills:
        raise ValueError("Profile must list at least one skill for fit scoring.")

    configured_weights = config.get("score_weights", {})
    if not isinstance(configured_weights, Mapping):
        raise ValueError("Config field 'score_weights' must be an object.")
    weights = DEFAULT_WEIGHTS.copy()
    for key, value in configured_weights.items():
        if key not in DEFAULT_WEIGHTS:
            raise ValueError(f"Unknown scoring weight {key!r}.")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Scoring weight {key!r} must be an integer.")
        weights[key] = value
    maximum = sum(weights[key] for key in ("skills", "role", "location", "seniority"))
    if maximum != 100 or any(weights[key] < 0 for key in weights):
        raise ValueError("Scoring weights must total 100 and cannot be negative.")

    searchable_text = f"{job.title} {job.description}"
    matching_skills = [skill for skill in skills if _has_phrase(searchable_text, skill)]
    skill_points = round(weights["skills"] * len(matching_skills) / len(skills))
    matched_skill_text = ", ".join(matching_skills) if matching_skills else "none"

    matched_primary = next((role for role in primary_roles if _has_phrase(job.title, role)), None)
    matched_secondary = next(
        (role for role in secondary_roles if _has_phrase(job.title, role)), None
    )
    if matched_primary:
        role_points = weights["role"]
        role_reason = f"primary role '{matched_primary}'"
    elif matched_secondary:
        role_points = round(weights["role"] * 0.72)
        role_reason = f"secondary role '{matched_secondary}'"
    else:
        role_points = 0
        role_reason = "no configured target role matched the title"

    location_status, location_detail = assess_location(job, config)
    if location_status == "allowed":
        location_points = weights["location"]
        location_reason = f"eligible region - {location_points}/{weights['location']} points"
    elif location_status == "unknown":
        location_points = weights["unknown_location"]
        location_reason = (
            f"unknown location - {location_points}/{weights['location']} points; "
            f"{location_detail.rstrip('.')}"
        )
    else:
        location_points = 0
        location_reason = (
            f"restricted location - 0/{weights['location']} points; "
            f"{location_detail.rstrip('.')}"
        )

    seniority = "standard"
    seniority_points = weights["seniority"]
    if any(_has_phrase(job.title, term) for term in high_stretch_terms):
        seniority = "high stretch"
        seniority_points = max(
            0, weights["seniority"] - weights["high_stretch_penalty"]
        )
    elif any(_has_phrase(job.title, term) for term in seniority_terms):
        seniority = "seniority stretch"
        seniority_points = max(
            0, weights["seniority"] - weights["senior_stretch_penalty"]
        )

    score = skill_points + role_points + location_points + seniority_points
    reasons = (
        f"Skills: {len(matching_skills)}/{len(skills)} matched "
        f"({matched_skill_text}) - {skill_points}/{weights['skills']} points.",
        f"Role fit: {role_reason} - {role_points}/{weights['role']} points.",
        f"Location: {location_reason}.",
        f"Seniority: {seniority} - {seniority_points}/{weights['seniority']} points.",
    )
    job.fit_score = score
    job.score_reasons = list(reasons)
    job.location_status = location_status if location_status != "restricted" else "unknown"
    job.location_reason = location_detail
    return FitScore(score=score, reasons=reasons)
