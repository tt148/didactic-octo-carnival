import sqlite3
from datetime import date

from remote_job_tracker.dashboard import (
    count_by_source,
    count_matching_skills,
    count_new_jobs_by_day,
    filter_jobs,
    nigeria_eligible_share,
    prepare_dashboard_jobs,
)
from remote_job_tracker.models import Job
from remote_job_tracker.storage import connect_database, save_jobs, update_status

CONFIG = {
    "title_include": ["it support", "technical support", "customer support"],
    "title_exclude": [],
    "location_allow": ["worldwide", "africa", "nigeria"],
    "location_deny": ["us", "usa", "united states", "canada", "uk"],
    "profile": {
        "skills": ["Linux", "Python", "help desk"],
        "skill_aliases": {"help desk": ["helpdesk", "service desk"]},
        "primary_roles": ["it support", "technical support"],
        "secondary_roles": [],
        "seniority_stretch_terms": ["senior"],
        "high_stretch_terms": ["director"],
    },
    "score_weights": {
        "skills": 50,
        "role": 25,
        "location": 15,
        "seniority": 10,
        "unknown_location": 5,
        "senior_stretch_penalty": 4,
        "high_stretch_penalty": 7,
    },
}


def make_job(
    title: str, *, source: str = "remotive", location: str = "Nigeria", description: str = ""
) -> Job:
    return Job(
        source=source,
        job_id=f"{source}-{title}",
        title=title,
        company="Example Co",
        location=location,
        url="https://example.com/job",
        posted="",
        description=description,
    )


def test_prepare_dashboard_rescores_relevant_jobs_and_preserves_status(tmp_path):
    db = connect_database(tmp_path / "jobs.db")
    job = make_job("IT Support Engineer", description="Linux Python service desk.")
    job.first_seen = "2026-10-20T00:00:00+00:00"
    save_jobs(db, [job])
    update_status(db, job.source, job.job_id, "saved")
    jobs = prepare_dashboard_jobs(db, CONFIG)
    assert len(jobs) == 1
    assert jobs[0].fit_score is not None
    assert jobs[0].status == "saved"
    assert len(jobs[0].score_reasons or []) == 4
    db.close()


def test_prepare_dashboard_omits_restricted_and_unmatched_legacy_rows(tmp_path):
    db = connect_database(tmp_path / "jobs.db")
    save_jobs(
        db,
        [
            make_job("US-based IT Support Engineer", location="Worldwide"),
            make_job("Customer Support Specialist", location="Nigeria"),
        ],
    )
    assert prepare_dashboard_jobs(db, CONFIG) == []
    db.close()


def test_dashboard_filters_and_trend_summaries():
    jobs = [
        make_job("IT Support Engineer", description="Linux Python service desk"),
        make_job("Senior Technical Support Engineer", source="jobicy", location="Anywhere"),
    ]
    jobs[0].fit_score = 80
    jobs[0].location_status = "allowed"
    jobs[0].first_seen = "2026-10-20T00:00:00+00:00"
    jobs[1].fit_score = 60
    jobs[1].location_status = "unknown"
    jobs[1].first_seen = "2026-10-20T13:00:00+00:00"
    filtered = filter_jobs(
        jobs,
        {"remotive", "jobicy"},
        {"new"},
        {"allowed"},
        50,
        "it support",
    )
    assert filtered == [jobs[0]]
    assert count_matching_skills(jobs, CONFIG["profile"]) == {
        "Linux": 1,
        "Python": 1,
        "help desk": 1,
    }
    assert count_by_source(jobs) == {"remotive": 1, "jobicy": 1}
    assert count_new_jobs_by_day(jobs) == {date(2026, 10, 20): 2}
    assert nigeria_eligible_share(jobs) == 0.5


def test_load_jobs_handles_legacy_schema_migration(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.execute(
        """CREATE TABLE jobs (
            source TEXT, job_id TEXT, title TEXT, company TEXT, location TEXT,
            url TEXT, posted TEXT, description TEXT, apply_email TEXT,
            status TEXT DEFAULT 'new', first_seen TEXT,
            PRIMARY KEY (source, job_id)
        )"""
    )
    db.execute(
        "INSERT INTO jobs (source, job_id, title, first_seen) VALUES (?, ?, ?, ?)",
        ("remotive", "old", "IT Support Engineer", "2026-01-01T00:00:00"),
    )
    db.commit()
    db.close()
    migrated = connect_database(path)
    jobs = prepare_dashboard_jobs(migrated, CONFIG)
    assert len(jobs) == 1
    assert jobs[0].first_seen == "2026-01-01T00:00:00"
    migrated.close()
