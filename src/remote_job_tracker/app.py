"""Streamlit dashboard for remote job listings."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing

import pandas as pd
import streamlit as st

from remote_job_tracker.dashboard import (
    count_by_source,
    count_matching_skills,
    count_new_jobs_by_day,
    filter_jobs,
    nigeria_eligible_share,
    prepare_dashboard_jobs,
)
from remote_job_tracker.paths import PROJECT_ROOT, data_directory
from remote_job_tracker.storage import (
    VALID_STATUSES,
    connect_database,
    load_source_collection_stats,
    update_status,
)

STATUS_OPTIONS = ("new", "saved", "applied", "ignored")
LOCATION_OPTIONS = ("allowed", "unknown")


def _job_key(source: str, job_id: str) -> str:
    return hashlib.sha256(f"{source}\0{job_id}".encode()).hexdigest()[:16]


def run_dashboard() -> None:
    st.set_page_config(page_title="Remote Job Market Tracker", layout="wide")
    st.title("Remote Job Market Tracker")
    st.caption("Remote roles matched to your profile. Scores include visible reasons.")

    try:
        config = json.loads((PROJECT_ROOT / "config.json").read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            raise ValueError("config.json must contain a JSON object.")
        with closing(connect_database(data_directory() / "jobs.db")) as db:
            source_stats = load_source_collection_stats(db)
            jobs = prepare_dashboard_jobs(db, config)
            st.subheader("Latest collection by source")
            if source_stats:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "Source": item.source,
                                "Fetched": item.fetched,
                                "Matched": item.matched,
                                "New": item.new,
                                "Status": f"Failed: {item.error}" if item.error else "OK",
                            }
                            for item in source_stats
                        ]
                    ),
                    hide_index=True,
                    use_container_width=True,
                )
            else:
                st.info("No collection counts yet. Run `python collector.py` to collect jobs.")
            if not jobs:
                st.info("No eligible job listings yet. Run `python collector.py` to collect jobs.")
                return

            st.sidebar.header("Filter jobs")
            selected_sources = set(
                st.sidebar.multiselect(
                    "Sources",
                    sorted({job.source for job in jobs}),
                    default=sorted({job.source for job in jobs}),
                )
            )
            selected_statuses = set(
                st.sidebar.multiselect(
                    "Status",
                    STATUS_OPTIONS,
                    default=list(STATUS_OPTIONS),
                )
            )
            selected_locations = set(
                st.sidebar.multiselect(
                    "Location eligibility",
                    LOCATION_OPTIONS,
                    default=list(LOCATION_OPTIONS),
                )
            )
            minimum_score = st.sidebar.slider("Minimum fit score", 0, 100, 0)
            search_text = st.sidebar.text_input("Search titles, companies, descriptions")
            filtered = filter_jobs(
                jobs,
                selected_sources,
                selected_statuses,
                selected_locations,
                minimum_score,
                search_text,
            )
            ranked = sorted(filtered, key=lambda job: job.fit_score or 0, reverse=True)

            first_column, second_column, third_column = st.columns(3)
            first_column.metric("Matching jobs", len(filtered))
            second_column.metric(
                "Best fit score",
                f"{ranked[0].fit_score}/100" if ranked else "—",
            )
            third_column.metric(
                "Location-eligible share",
                f"{nigeria_eligible_share(filtered):.0%}",
            )
            st.caption("Share matching configured allowed regions; unknown locations do not count.")

            st.subheader("Hiring trends")
            skill_counts = count_matching_skills(
                filtered,
                config["profile"],
            )
            source_counts = count_by_source(filtered)
            daily_counts = count_new_jobs_by_day(filtered)
            skill_column, source_column = st.columns(2)
            with skill_column:
                st.markdown("**Most requested profile skills**")
                if skill_counts:
                    st.bar_chart(
                        pd.Series(skill_counts).head(12),
                        horizontal=True,
                        x_label="Listings mentioning the skill",
                    )
                else:
                    st.info("No configured skills matched these listings.")
            with source_column:
                st.markdown("**Jobs per source**")
                if source_counts:
                    st.bar_chart(pd.Series(source_counts), x_label="Listings")
                else:
                    st.info("No listings match the selected filters.")
            st.markdown("**New jobs per day**")
            if daily_counts:
                st.line_chart(
                    pd.Series(daily_counts, dtype="int64"),
                    x_label="First seen",
                    y_label="New listings",
                )
            else:
                st.info("No first-seen dates are available for these listings.")

            st.subheader("Top matches")
            if not ranked:
                st.info("No jobs match the selected filters.")
            for job in ranked[:30]:
                key = _job_key(job.source, job.job_id)
                with st.container(border=True):
                    heading, score_column = st.columns([5, 1])
                    heading.markdown(f"### {job.title}")
                    heading.caption(
                        f"{job.company} · {job.location or 'Location unknown'} · "
                        f"{job.source} · {job.location_status}"
                    )
                    score_column.metric("Fit", f"{job.fit_score}/100")
                    if job.url:
                        st.link_button("View original listing", job.url)
                    with st.expander("Why this score?"):
                        for reason in job.score_reasons or []:
                            st.write(f"- {reason}")
                        if job.location_reason:
                            st.caption(f"Location assessment: {job.location_reason}")
                        st.write(job.description or "No description provided by the source.")
                    with st.form(f"status-{key}"):
                        selected_status = st.selectbox(
                            "Application status",
                            sorted(VALID_STATUSES),
                            index=sorted(VALID_STATUSES).index(job.status),
                            key=f"status-select-{key}",
                        )
                        if st.form_submit_button("Save status"):
                            if not update_status(db, job.source, job.job_id, selected_status):
                                st.error("Could not update this job; it may have been removed.")
                            else:
                                st.rerun()
    except (OSError, json.JSONDecodeError, sqlite3.Error, ValueError) as error:
        st.error(f"Could not load the job dashboard: {error}")


if __name__ == "__main__":
    run_dashboard()
