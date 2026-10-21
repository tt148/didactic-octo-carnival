import sqlite3

import pytest

from remote_job_tracker.models import Job
from remote_job_tracker.storage import (
    connect_database,
    save_jobs,
    update_fit_score,
    update_status,
)


def make_job() -> Job:
    return Job(
        source="remotive",
        job_id="123",
        title="IT Support Engineer",
        company="Example Co",
        location="Worldwide",
        url="https://example.com/job",
        posted="2026-10-20",
        description="Support Linux systems.",
        location_status="allowed",
        location_reason="Location matches an allowed region.",
    )


def test_save_jobs_deduplicates_and_preserves_status_and_first_seen(tmp_path):
    db = connect_database(tmp_path / "jobs.db")
    job = make_job()
    assert save_jobs(db, [job, job]) == [job]
    first_seen = db.execute("SELECT first_seen FROM jobs").fetchone()["first_seen"]
    assert update_status(db, job.source, job.job_id, "saved")
    job.fit_score = 87
    job.score_reasons = ["Skills: 3/8 matched - 19/50 points."]
    assert save_jobs(db, [job]) == []
    assert save_jobs(db, [job]) == []
    saved = db.execute(
        "SELECT status, first_seen, fit_score, score_reasons FROM jobs"
    ).fetchone()
    assert saved["status"] == "saved"
    assert saved["first_seen"] == first_seen
    assert saved["fit_score"] == 87
    assert "3/8 matched" in saved["score_reasons"]
    assert update_fit_score(db, job)
    scored = db.execute("SELECT fit_score, score_reasons FROM jobs").fetchone()
    assert scored["fit_score"] == 87
    assert "3/8 matched" in scored["score_reasons"]
    db.close()


def test_legacy_database_is_migrated_without_losing_rows(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """CREATE TABLE jobs (
            source TEXT, job_id TEXT, title TEXT, company TEXT, location TEXT,
            url TEXT, posted TEXT, description TEXT, apply_email TEXT,
            status TEXT DEFAULT 'new', first_seen TEXT,
            PRIMARY KEY (source, job_id)
        )"""
    )
    legacy.execute(
        "INSERT INTO jobs (source, job_id, title, first_seen) VALUES (?, ?, ?, ?)",
        ("remotive", "old-1", "Existing job", "2026-01-01T00:00:00"),
    )
    legacy.commit()
    legacy.close()

    db = connect_database(path)
    row = db.execute(
        "SELECT title, status, first_seen, location_status FROM jobs WHERE job_id = 'old-1'"
    ).fetchone()
    assert row["title"] == "Existing job"
    assert row["status"] == "new"
    assert row["first_seen"] == "2026-01-01T00:00:00"
    assert row["location_status"] == "unknown"
    db.close()


def test_update_status_rejects_invalid_values(tmp_path):
    db = connect_database(tmp_path / "jobs.db")
    with pytest.raises(ValueError, match="Invalid job status"):
        update_status(db, "remotive", "123", "submitted")
    db.close()
