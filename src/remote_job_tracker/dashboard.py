"""Dashboard data preparation and filters."""

from __future__ import annotations

import sqlite3
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date

from remote_job_tracker.filters import assess_location, title_matches
from remote_job_tracker.models import Job
from remote_job_tracker.scoring import matching_skills, score_job
from remote_job_tracker.storage import load_jobs, update_fit_score


def prepare_dashboard_jobs(
    db: sqlite3.Connection, config: Mapping[str, object]
) -> list[Job]:
    """Re-score saved listings and return currently relevant, non-restricted roles."""
    profile = config.get("profile")
    if not isinstance(profile, Mapping):
        raise ValueError("Config must include a profile object.")
    jobs = load_jobs(db)
    candidates: list[Job] = []
    for job in jobs:
        score_job(job, config)
        update_fit_score(db, job)
        location_status, _ = assess_location(job, config)
        if title_matches(job, config) and location_status != "restricted":
            candidates.append(job)
    return candidates


def filter_jobs(
    jobs: Sequence[Job],
    sources: set[str],
    statuses: set[str],
    locations: set[str],
    minimum_score: int,
    search_text: str,
) -> list[Job]:
    query = search_text.casefold().strip()
    return [
        job
        for job in jobs
        if job.source in sources
        and job.status in statuses
        and job.location_status in locations
        and (job.fit_score or 0) >= minimum_score
        and (
            not query
            or query in job.title.casefold()
            or query in job.company.casefold()
            or query in job.description.casefold()
        )
    ]


def count_matching_skills(
    jobs: Sequence[Job], profile: Mapping[str, object]
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for job in jobs:
        counts.update(matching_skills(job, profile).keys())
    return dict(counts.most_common())


def count_by_source(jobs: Sequence[Job]) -> dict[str, int]:
    return dict(Counter(job.source for job in jobs).most_common())


def count_new_jobs_by_day(jobs: Sequence[Job]) -> dict[date, int]:
    counts: Counter[date] = Counter()
    for job in jobs:
        if job.first_seen:
            try:
                counts[date.fromisoformat(job.first_seen[:10])] += 1
            except ValueError:
                continue
    return dict(sorted(counts.items()))


def nigeria_eligible_share(jobs: Sequence[Job]) -> float:
    if not jobs:
        return 0.0
    return sum(job.location_status == "allowed" for job in jobs) / len(jobs)
