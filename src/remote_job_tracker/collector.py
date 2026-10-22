"""Collection orchestration and command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Mapping
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from remote_job_tracker.filters import keep_job
from remote_job_tracker.models import Job, SourceCollectionStats
from remote_job_tracker.paths import PROJECT_ROOT, data_directory
from remote_job_tracker.scoring import score_job
from remote_job_tracker.sources import SOURCES
from remote_job_tracker.storage import (
    connect_database,
    export_csv,
    save_jobs,
    save_source_collection_stats,
)


def collect_jobs(
    config: Mapping[str, object],
) -> tuple[list[Job], list[str], list[SourceCollectionStats]]:
    jobs: list[Job] = []
    failures: list[str] = []
    source_stats: list[SourceCollectionStats] = []
    successful_sources = 0
    for name, source in SOURCES.items():
        try:
            found = source(config)
        except Exception as error:
            message = f"[{name}] FAILED: {error}"
            print(message, file=sys.stderr)
            failures.append(message)
            source_stats.append(SourceCollectionStats(name, 0, 0, 0, str(error)))
            continue
        successful_sources += 1
        matched = [job for job in found if keep_job(job, config)]
        source_stats.append(SourceCollectionStats(name, len(found), len(matched), 0))
        jobs.extend(matched)
    if successful_sources == 0:
        raise RuntimeError("All job sources failed; no collection was saved.")
    for job in jobs:
        score_job(job, config)
    return jobs, failures, source_stats


def run_collection(config_path: Path, database_path: Path, csv_path: Path) -> None:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Config file must contain a JSON object.")
    matched, failures, source_stats = collect_jobs(config)
    with closing(connect_database(database_path)) as db:
        new_jobs = save_jobs(db, matched)
        new_counts = Counter(job.source for job in new_jobs)
        source_stats = [replace(stats, new=new_counts[stats.source]) for stats in source_stats]
        save_source_collection_stats(db, source_stats)
        export_csv(db, csv_path)
    print("\nCollection results:")
    for stats in source_stats:
        print(f"[{stats.source}] fetched {stats.fetched}, matched {stats.matched}, new {stats.new}")
    if failures:
        print(f"{len(failures)} source(s) failed; see errors above.", file=sys.stderr)
    print(f"\n{len(matched)} matched filters, {len(new_jobs)} new. Saved to {csv_path}\n")
    for job in new_jobs:
        email = f"  email: {job.apply_email}" if job.apply_email else ""
        print(
            f"- {job.title} | {job.company} | {job.location or 'n/a'} "
            f"({job.source}) [{job.location_status}]{email}\n  {job.url}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect remote job listings.")
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "config.json")
    parser.add_argument("--database", type=Path, default=data_directory() / "jobs.db")
    parser.add_argument("--csv", type=Path, default=data_directory() / "jobs.csv")
    args = parser.parse_args()
    try:
        run_collection(args.config, args.database, args.csv)
    except (OSError, ValueError, RuntimeError) as error:
        parser.exit(1, f"Collection failed: {error}\n")


if __name__ == "__main__":
    main()
