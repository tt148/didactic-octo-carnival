"""SQLite persistence and CSV export for collected jobs."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from remote_job_tracker.models import Job, SourceCollectionStats

VALID_STATUSES = {"new", "saved", "applied", "ignored"}
CSV_COLUMNS = (
    "status",
    "title",
    "company",
    "location",
    "location_status",
    "apply_email",
    "url",
    "source",
    "posted",
    "first_seen",
    "fit_score",
    "score_reasons",
)


def connect_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute(
        """CREATE TABLE IF NOT EXISTS jobs (
            source TEXT NOT NULL,
            job_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            location TEXT NOT NULL,
            url TEXT NOT NULL,
            posted TEXT NOT NULL,
            description TEXT NOT NULL,
            apply_email TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'saved', 'applied', 'ignored')),
            first_seen TEXT NOT NULL,
            location_status TEXT NOT NULL DEFAULT 'unknown',
            location_reason TEXT NOT NULL DEFAULT '',
            fit_score INTEGER,
            score_reasons TEXT NOT NULL DEFAULT '[]',
            PRIMARY KEY (source, job_id)
        )"""
    )
    db.execute(
        """CREATE TABLE IF NOT EXISTS source_collection_stats (
            source TEXT PRIMARY KEY,
            fetched INTEGER NOT NULL,
            matched INTEGER NOT NULL,
            new INTEGER NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            collected_at TEXT NOT NULL
        )"""
    )
    _migrate_legacy_jobs_table(db)
    return db


def save_source_collection_stats(
    db: sqlite3.Connection, stats: Iterable[SourceCollectionStats]
) -> None:
    collected_at = datetime.now(UTC).isoformat(timespec="seconds")
    with db:
        db.execute("DELETE FROM source_collection_stats")
        db.executemany(
            """INSERT INTO source_collection_stats
            (source, fetched, matched, new, error, collected_at)
            VALUES (?, ?, ?, ?, ?, ?)""",
            [
                (
                    item.source,
                    item.fetched,
                    item.matched,
                    item.new,
                    item.error,
                    collected_at,
                )
                for item in stats
            ],
        )


def load_source_collection_stats(
    db: sqlite3.Connection,
) -> list[SourceCollectionStats]:
    rows = db.execute(
        """SELECT source, fetched, matched, new, error
        FROM source_collection_stats ORDER BY source"""
    )
    return [
        SourceCollectionStats(
            source=row["source"],
            fetched=row["fetched"],
            matched=row["matched"],
            new=row["new"],
            error=row["error"],
        )
        for row in rows
    ]


def _migrate_legacy_jobs_table(db: sqlite3.Connection) -> None:
    columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
    additions = {
        "location_status": "TEXT NOT NULL DEFAULT 'unknown'",
        "location_reason": "TEXT NOT NULL DEFAULT ''",
        "fit_score": "INTEGER",
        "score_reasons": "TEXT NOT NULL DEFAULT '[]'",
    }
    for name, declaration in additions.items():
        if name not in columns:
            db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
    db.commit()


def save_jobs(db: sqlite3.Connection, jobs: Iterable[Job]) -> list[Job]:
    now = datetime.now(UTC).isoformat(timespec="seconds")
    inserted: list[Job] = []
    with db:
        for job in jobs:
            cursor = db.execute(
                """INSERT OR IGNORE INTO jobs (
                    source, job_id, title, company, location, url, posted, description,
                    apply_email, status, first_seen, location_status, location_reason,
                    fit_score, score_reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?, ?, ?)""",
                (
                    job.source,
                    job.job_id,
                    job.title,
                    job.company,
                    job.location,
                    job.url,
                    job.posted,
                    job.description,
                    job.apply_email,
                    now,
                    job.location_status,
                    job.location_reason,
                    job.fit_score,
                    encode_score_reasons(job.score_reasons or []),
                ),
            )
            if cursor.rowcount:
                inserted.append(job)
            db.execute(
                """UPDATE jobs
                SET title = ?, company = ?, location = ?, url = ?, posted = ?,
                    description = ?, apply_email = ?, location_status = ?, location_reason = ?,
                    fit_score = ?, score_reasons = ?
                WHERE source = ? AND job_id = ?""",
                (
                    job.title,
                    job.company,
                    job.location,
                    job.url,
                    job.posted,
                    job.description,
                    job.apply_email,
                    job.location_status,
                    job.location_reason,
                    job.fit_score,
                    encode_score_reasons(job.score_reasons or []),
                    job.source,
                    job.job_id,
                ),
            )
    return inserted


def update_fit_score(db: sqlite3.Connection, job: Job) -> bool:
    if job.fit_score is None:
        raise ValueError("Cannot store a job without a fit score.")
    with db:
        cursor = db.execute(
            """UPDATE jobs
            SET fit_score = ?, score_reasons = ?, location_status = ?, location_reason = ?
            WHERE source = ? AND job_id = ?""",
            (
                job.fit_score,
                encode_score_reasons(job.score_reasons or []),
                job.location_status,
                job.location_reason,
                job.source,
                job.job_id,
            ),
        )
    return cursor.rowcount == 1


def load_jobs(db: sqlite3.Connection) -> list[Job]:
    rows = db.execute(
        """SELECT source, job_id, title, company, location, url, posted, description,
        apply_email, location_status, location_reason, fit_score, status, first_seen
        FROM jobs ORDER BY first_seen DESC"""
    )
    return [
        Job(
            source=row["source"],
            job_id=row["job_id"],
            title=row["title"] or "",
            company=row["company"] or "",
            location=row["location"] or "",
            url=row["url"] or "",
            posted=row["posted"] or "",
            description=row["description"] or "",
            apply_email=row["apply_email"] or "",
            location_status=row["location_status"],
            location_reason=row["location_reason"],
            fit_score=row["fit_score"],
            status=row["status"],
            first_seen=row["first_seen"],
        )
        for row in rows
    ]


def update_status(db: sqlite3.Connection, source: str, job_id: str, status: str) -> bool:
    if status not in VALID_STATUSES:
        expected = ", ".join(sorted(VALID_STATUSES))
        raise ValueError(f"Invalid job status {status!r}; expected one of: {expected}.")
    with db:
        cursor = db.execute(
            "UPDATE jobs SET status = ? WHERE source = ? AND job_id = ?",
            (status, source, job_id),
        )
    return cursor.rowcount == 1


def export_csv(db: sqlite3.Connection, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = db.execute(f"SELECT {', '.join(CSV_COLUMNS)} FROM jobs ORDER BY first_seen DESC")
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_COLUMNS)
        writer.writerows(rows.fetchall())


def encode_score_reasons(reasons: list[str]) -> str:
    return json.dumps(reasons, ensure_ascii=False)
