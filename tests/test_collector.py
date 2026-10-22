import json
import sqlite3

from remote_job_tracker import collector
from remote_job_tracker.models import Job

CONFIG = {
    "title_include": ["it support"],
    "title_exclude": [],
    "location_allow": ["nigeria"],
    "location_deny": ["united states"],
    "profile": {
        "skills": ["Linux"],
        "skill_aliases": {},
        "skill_match_aliases_only": [],
        "primary_roles": ["it support"],
        "secondary_roles": [],
        "seniority_stretch_terms": [],
        "high_stretch_terms": [],
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


def make_job(source: str, job_id: str, title: str) -> Job:
    return Job(
        source=source,
        job_id=job_id,
        title=title,
        company="Example Co",
        location="Nigeria",
        url=f"https://example.com/{job_id}",
        posted="",
        description="Linux support.",
    )


def test_run_collection_reports_and_persists_per_source_counts(tmp_path, monkeypatch, capsys):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(CONFIG), encoding="utf-8")
    monkeypatch.setattr(
        collector,
        "SOURCES",
        {
            "remoteok": lambda _: [
                make_job("remoteok", "match", "IT Support Engineer"),
                make_job("remoteok", "miss", "Product Designer"),
            ],
            "remotive": lambda _: [make_job("remotive", "miss", "Product Designer")],
        },
    )
    database_path = tmp_path / "data" / "jobs.db"
    csv_path = tmp_path / "data" / "jobs.csv"

    collector.run_collection(config_path, database_path, csv_path)

    output = capsys.readouterr().out
    assert "[remoteok] fetched 2, matched 1, new 1" in output
    assert "[remotive] fetched 1, matched 0, new 0" in output
    assert csv_path.exists()
    with sqlite3.connect(database_path) as db:
        rows = db.execute(
            "SELECT source, fetched, matched, new FROM source_collection_stats ORDER BY source"
        ).fetchall()
    assert rows == [("remoteok", 2, 1, 1), ("remotive", 1, 0, 0)]
