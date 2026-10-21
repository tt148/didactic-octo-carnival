"""Collection orchestration and command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from remote_job_tracker.filters import keep_job
from remote_job_tracker.models import Job
from remote_job_tracker.sources import SOURCES
from remote_job_tracker.storage import connect_database, export_csv, save_jobs

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def collect_jobs(config: Mapping[str, object]) -> tuple[list[Job], list[str]]:
    jobs: list[Job] = []
    failures: list[str] = []
    successful_sources = 0
    for name, source in SOURCES.items():
        try:
            found = source(config)
        except Exception as error:
            message = f"[{name}] FAILED: {error}"
            print(message, file=sys.stderr)
            failures.append(message)
            continue
        successful_sources += 1
        print(f"[{name}] fetched {len(found)}")
        jobs.extend(found)
    if successful_sources == 0:
        raise RuntimeError("All job sources failed; no collection was saved.")
    return [job for job in jobs if keep_job(job, config)], failures


def run_collection(config_path: Path, database_path: Path, csv_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config file must contain a JSON object.")
    matched, failures = collect_jobs(config)
    with closing(connect_database(database_path)) as db:
        new_jobs = save_jobs(db, matched)
        export_csv(db, csv_path)
    print(f"\n{len(matched)} matched filters, {len(new_jobs)} new. Saved to {csv_path}\n")
    if failures:
        print(f"{len(failures)} source(s) failed; see errors above.", file=sys.stderr)
    for job in new_jobs:
        email = f"  email: {job.apply_email}" if job.apply_email else ""
        print(
            f"- {job.title} | {job.company} | {job.location or 'n/a'} "
            f"({job.source}) [{job.location_status}]{email}\n  {job.url}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect remote job listings.")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    parser.add_argument("--database", type=Path, default=PROJECT_ROOT / "jobs.db")
    parser.add_argument("--csv", type=Path, default=PROJECT_ROOT / "jobs.csv")
    args = parser.parse_args()
    try:
        run_collection(args.config, args.database, args.csv)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Collection failed: {error}\n")


if __name__ == "__main__":
    main()
