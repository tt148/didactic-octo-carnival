#!/usr/bin/env python3
"""Job collector: pulls remote job listings, filters them, removes duplicates,
and saves them to SQLite (jobs.db) and a CSV you can open in Excel (jobs.csv).

Run:   python collector.py
Edit config.json to change search terms, title filters and location rules.
Uses only the Python standard library, so nothing to install.
"""
import csv
import html
import json
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).parent
HEADERS = {"User-Agent": "Mozilla/5.0 (personal job collector)"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
TAG_RE = re.compile(r"<[^>]+>")
BAD_EMAIL_RE = re.compile(r"(no-?reply|example\.com|\.png|\.jpg|\.gif)", re.I)


@dataclass
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


# ---------- helpers ----------

def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def clean(text: str) -> str:
    text = html.unescape(TAG_RE.sub(" ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def find_email(raw: str) -> str:
    for m in EMAIL_RE.findall(html.unescape(raw or "")):
        if not BAD_EMAIL_RE.search(m):
            return m
    return ""


def make_job(source, job_id, title, company, location, url, posted, raw_desc) -> Job:
    return Job(
        source=source,
        job_id=str(job_id),
        title=clean(title),
        company=clean(company),
        location=clean(location),
        url=url or "",
        posted=str(posted or ""),
        description=clean(raw_desc)[:4000],
        apply_email=find_email(raw_desc),
    )


# ---------- sources (each returns a list of Job) ----------

def from_remotive(cfg):
    jobs = []
    for term in cfg["search_terms"]:
        data = json.loads(fetch(f"https://remotive.com/api/remote-jobs?search={quote(term)}"))
        for j in data.get("jobs", []):
            jobs.append(make_job("remotive", j.get("id"), j.get("title"), j.get("company_name"),
                                 j.get("candidate_required_location"), j.get("url"),
                                 j.get("publication_date"), j.get("description")))
    return jobs


def from_remoteok(cfg):
    data = json.loads(fetch("https://remoteok.com/api"))
    jobs = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:  # first item is a legal notice
            continue
        jobs.append(make_job("remoteok", j.get("id"), j.get("position"), j.get("company"),
                             j.get("location") or "Worldwide", j.get("url"), j.get("date"),
                             j.get("description")))
    return jobs


def from_jobicy(cfg):
    jobs = []
    for term in cfg["search_terms"]:
        data = json.loads(fetch(f"https://jobicy.com/api/v2/remote-jobs?count=50&tag={quote(term)}"))
        for j in data.get("jobs", []):
            jobs.append(make_job("jobicy", j.get("id"), j.get("jobTitle"), j.get("companyName"),
                                 j.get("jobGeo"), j.get("url"), j.get("pubDate"),
                                 j.get("jobDescription") or j.get("jobExcerpt")))
    return jobs


def from_wwr(cfg):
    jobs = []
    for feed in cfg["wwr_feeds"]:
        root = ET.fromstring(fetch(feed))
        for item in root.iter("item"):
            raw_title = item.findtext("title") or ""
            company, _, title = raw_title.partition(": ")  # WWR format: "Company: Job title"
            if not title:
                company, title = "", raw_title
            link = item.findtext("link") or ""
            jobs.append(make_job("weworkremotely", item.findtext("guid") or link, title, company,
                                 item.findtext("region") or "", link, item.findtext("pubDate"),
                                 item.findtext("description")))
    return jobs


SOURCES = {
    "remotive": from_remotive,
    "remoteok": from_remoteok,
    "jobicy": from_jobicy,
    "weworkremotely": from_wwr,
}


# ---------- filtering ----------

def keep(job: Job, cfg) -> bool:
    title = job.title.lower()
    if not any(k in title for k in cfg["title_include"]):
        return False
    if any(k in title for k in cfg["title_exclude"]):
        return False
    loc = job.location.lower()
    denied = any(k in loc for k in cfg["location_deny"])
    allowed = any(k in loc for k in cfg["location_allow"])
    return not (denied and not allowed)  # empty location is kept


# ---------- storage ----------

def open_db(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            source TEXT, job_id TEXT, title TEXT, company TEXT, location TEXT,
            url TEXT, posted TEXT, description TEXT, apply_email TEXT,
            status TEXT DEFAULT 'new', first_seen TEXT,
            PRIMARY KEY (source, job_id))"""
    )
    return db


def save(db, jobs):
    new = []
    now = datetime.now().isoformat(timespec="seconds")
    for j in jobs:
        cur = db.execute(
            """INSERT OR IGNORE INTO jobs
               (source, job_id, title, company, location, url, posted, description, apply_email, first_seen)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (j.source, j.job_id, j.title, j.company, j.location, j.url, j.posted,
             j.description, j.apply_email, now),
        )
        if cur.rowcount:
            new.append(j)
    db.commit()
    return new


def export_csv(db, path: Path):
    cur = db.execute(
        "SELECT status, title, company, location, apply_email, url, source, posted, first_seen "
        "FROM jobs ORDER BY first_seen DESC"
    )
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow([c[0] for c in cur.description])
        w.writerows(cur.fetchall())


# ---------- main ----------

def main():
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    collected = []
    for name, fn in SOURCES.items():
        try:
            found = fn(cfg)
            print(f"[{name}] fetched {len(found)}")
            collected.extend(found)
        except Exception as e:  # one broken source must not stop the others
            print(f"[{name}] FAILED: {e}")

    matched = [j for j in collected if keep(j, cfg)]
    db = open_db(HERE / "jobs.db")
    new = save(db, matched)
    export_csv(db, HERE / "jobs.csv")

    print(f"\n{len(matched)} matched filters, {len(new)} new. Saved to jobs.csv\n")
    for j in new:
        email = f"  email: {j.apply_email}" if j.apply_email else ""
        print(f"- {j.title} | {j.company} | {j.location or 'n/a'} ({j.source}){email}\n  {j.url}")


if __name__ == "__main__":
    main()
