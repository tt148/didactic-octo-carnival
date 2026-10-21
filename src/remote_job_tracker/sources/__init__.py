"""Job-board source adapters with a consistent interface."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from remote_job_tracker.http import fetch_bytes
from remote_job_tracker.models import Job
from remote_job_tracker.sources import jobicy, remoteok, remotive, weworkremotely

Fetcher = Callable[[str], bytes]
Source = Callable[[Mapping[str, object], Fetcher], list[Job]]

SOURCES: dict[str, Source] = {
    "remotive": remotive.fetch_jobs,
    "remoteok": remoteok.fetch_jobs,
    "jobicy": jobicy.fetch_jobs,
    "weworkremotely": weworkremotely.fetch_jobs,
}


def collect_all(
    config: Mapping[str, object], fetcher: Fetcher = fetch_bytes
) -> dict[str, list[Job]]:
    return {name: source(config, fetcher) for name, source in SOURCES.items()}
