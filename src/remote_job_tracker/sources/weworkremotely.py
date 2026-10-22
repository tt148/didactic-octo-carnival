"""Adapter for We Work Remotely RSS category feeds."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from xml.etree import ElementTree

from remote_job_tracker.http import fetch_bytes
from remote_job_tracker.models import Job, make_job

Fetcher = Callable[[str], bytes]


def fetch_jobs(config: Mapping[str, object], fetcher: Fetcher = fetch_bytes) -> list[Job]:
    feeds = config.get("wwr_feeds", [])
    if not isinstance(feeds, list):
        raise ValueError("We Work Remotely config 'wwr_feeds' must be a list.")
    jobs: list[Job] = []
    for feed in feeds:
        root = ElementTree.fromstring(fetcher(str(feed)))
        for item in root.iter("item"):
            raw_title = item.findtext("title") or ""
            company, separator, title = raw_title.partition(": ")
            if not separator:
                company, title = "", raw_title
            link = item.findtext("link") or ""
            jobs.append(
                make_job(
                    "weworkremotely",
                    item.findtext("guid") or link,
                    title,
                    company,
                    item.findtext("region") or "",
                    link,
                    item.findtext("pubDate"),
                    item.findtext("description"),
                )
            )
    return jobs
