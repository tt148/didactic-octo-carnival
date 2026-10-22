"""Adapter for the Jobicy public jobs API."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from urllib.parse import urlencode

from remote_job_tracker.http import fetch_bytes
from remote_job_tracker.models import Job, make_job

Fetcher = Callable[[str], bytes]
API_URL = "https://jobicy.com/api/v2/remote-jobs"


def fetch_jobs(config: Mapping[str, object], fetcher: Fetcher = fetch_bytes) -> list[Job]:
    search_terms = config.get("search_terms", [])
    if not isinstance(search_terms, list):
        raise ValueError("Jobicy config 'search_terms' must be a list.")
    jobs: list[Job] = []
    for term in search_terms:
        url = f"{API_URL}?{urlencode({'count': 50, 'tag': str(term)})}"
        data = json.loads(fetcher(url))
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), list):
            raise ValueError("Jobicy response must contain a jobs list.")
        for item in data["jobs"]:
            if not isinstance(item, dict):
                continue
            jobs.append(
                make_job(
                    "jobicy",
                    item.get("id"),
                    item.get("jobTitle"),
                    item.get("companyName"),
                    item.get("jobGeo"),
                    item.get("url"),
                    item.get("pubDate"),
                    item.get("jobDescription") or item.get("jobExcerpt"),
                )
            )
    return jobs
