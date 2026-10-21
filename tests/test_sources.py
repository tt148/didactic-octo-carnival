import json

import pytest

from remote_job_tracker.sources import jobicy, remoteok, remotive, weworkremotely


def as_bytes(payload):
    return json.dumps(payload).encode()


def test_remotive_maps_actual_api_shape():
    data = {
        "job-count": 1,
        "jobs": [
            {
                "id": 42,
                "title": "IT Support Engineer",
                "company_name": "Example Co",
                "candidate_required_location": "Worldwide",
                "url": "https://example.com/job",
                "publication_date": "2026-10-20",
                "description": "<p>Contact hiring@example.org</p>",
            }
        ],
    }
    jobs = remotive.fetch_jobs({"search_terms": ["IT support"]}, lambda _: as_bytes(data))
    assert len(jobs) == 1
    assert jobs[0].job_id == "42"
    assert jobs[0].apply_email == "hiring@example.org"
    assert jobs[0].description == "Contact hiring@example.org"


def test_remoteok_skips_legal_notice_and_leaves_missing_location_unknown():
    data = [
        {"legal": "API terms"},
        {
            "id": 9,
            "position": "Linux Support Engineer",
            "company": "Example Co",
            "url": "https://example.com/job",
            "date": "2026-10-20",
        },
    ]
    jobs = remoteok.fetch_jobs({}, lambda _: as_bytes(data))
    assert len(jobs) == 1
    assert jobs[0].location == ""


def test_jobicy_maps_current_response_keys():
    data = {
        "success": True,
        "jobCount": 1,
        "jobs": [
            {
                "id": 17,
                "jobTitle": "IT Administrator",
                "companyName": "Example Co",
                "jobGeo": "Nigeria",
                "url": "https://example.com/job",
                "pubDate": "2026-10-20",
                "jobDescription": "Maintain Linux systems.",
            }
        ],
    }
    jobs = jobicy.fetch_jobs({"search_terms": ["it support"]}, lambda _: as_bytes(data))
    assert jobs[0].title == "IT Administrator"
    assert jobs[0].location == "Nigeria"


def test_weworkremotely_parses_rss_item():
    payload = b"""<?xml version="1.0"?>
    <rss><channel><item>
      <guid>job-1</guid><title>Example Co: IT Support Engineer</title>
      <link>https://example.com/job</link><region>Worldwide</region>
      <pubDate>Tue, 20 Oct 2026 00:00:00 GMT</pubDate>
      <description><![CDATA[<p>Technical support.</p>]]></description>
    </item></channel></rss>"""
    jobs = weworkremotely.fetch_jobs(
        {"wwr_feeds": ["https://example.com/feed"]}, lambda _: payload
    )
    assert jobs[0].company == "Example Co"
    assert jobs[0].title == "IT Support Engineer"
    assert jobs[0].location == "Worldwide"


def test_sources_reject_unexpected_response_shapes():
    with pytest.raises(ValueError, match="jobs list"):
        remotive.fetch_jobs({"search_terms": ["support"]}, lambda _: b'{"jobs": null}')
