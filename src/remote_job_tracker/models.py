"""Shared job model and text normalization."""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from typing import Literal

LocationStatus = Literal["allowed", "unknown", "restricted"]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BAD_EMAIL_RE = re.compile(r"(no-?reply|example\.com|\.png|\.jpg|\.gif)", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class Job:
    source: str
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted: str
    description: str
    apply_email: str = ""
    location_status: LocationStatus = "unknown"
    location_reason: str = "Location has not been assessed."
    fit_score: int | None = None
    score_reasons: list[str] | None = None
    status: Literal["new", "saved", "applied", "ignored"] = "new"
    first_seen: str = ""


@dataclass(frozen=True, slots=True)
class SourceCollectionStats:
    source: str
    fetched: int
    matched: int
    new: int
    error: str = ""


def clean_text(value: object) -> str:
    """Convert a plain or HTML string to readable text."""
    if not isinstance(value, str):
        return ""
    text = html.unescape(TAG_RE.sub(" ", value))
    return re.sub(r"\s+", " ", text).strip()


def find_email(raw: str) -> str:
    for match in EMAIL_RE.findall(html.unescape(raw or "")):
        if not BAD_EMAIL_RE.search(match):
            return match
    return ""


def make_job(
    source: str,
    job_id: object,
    title: object,
    company: object,
    location: object,
    url: object,
    posted: object,
    raw_description: object,
) -> Job:
    clean_title = clean_text(title)
    clean_company = clean_text(company)
    clean_url = clean_text(url)
    clean_posted = clean_text(posted)
    raw_desc = raw_description if isinstance(raw_description, str) else ""
    description = clean_text(raw_desc)
    identity = job_id or clean_url
    if not identity:
        identity = hashlib.sha256(
            f"{clean_title}\0{clean_company}\0{clean_posted}".encode()
        ).hexdigest()
    return Job(
        source=source,
        job_id=str(identity),
        title=clean_title,
        company=clean_company,
        location=clean_text(location),
        url=clean_url,
        posted=clean_posted,
        description=description,
        apply_email=find_email(raw_desc),
    )
