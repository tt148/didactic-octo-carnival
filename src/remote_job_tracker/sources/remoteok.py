"""Adapter for the Remote OK public jobs API."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from remote_job_tracker.http import fetch_bytes
from remote_job_tracker.models import Job, make_job

Fetcher = Callable[[str], bytes]
API_URL = "https://remoteok.com/api"


def fetch_jobs(
    config: Mapping[str, object], fetcher: Fetcher = fetch_bytes
) -> list[Job]:
    del config
    data = json.loads(fetcher(API_URL))
    if not isinstance(data, list):
        raise ValueError("Remote OK response must be a list.")
    jobs: list[Job] = []
    for item in data:
        if not isinstance(item, dict) or "position" not in item:
            continue
        jobs.append(
            make_job(
                "remoteok",
                item.get("id"),
                item.get("position"),
                item.get("company"),
                item.get("location"),
                item.get("url"),
                item.get("date"),
                item.get("description"),
            )
        )
    return jobs
