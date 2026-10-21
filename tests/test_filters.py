from remote_job_tracker.filters import assess_location, keep_job
from remote_job_tracker.models import Job


def make_job(title: str, location: str = "", description: str = "") -> Job:
    return Job(
        source="test",
        job_id="1",
        title=title,
        company="Example Co",
        location=location,
        url="https://example.com/job",
        posted="",
        description=description,
    )


CONFIG = {
    "title_include": [
        "it support",
        "help desk",
        "helpdesk",
        "service desk",
        "technical support",
        "tech support",
        "desktop support",
        "support engineer",
        "support specialist",
        "support technician",
        "system admin",
        "sysadmin",
        "it technician",
        "it administrator",
        "network",
    ],
    "location_allow": ["worldwide", "anywhere", "global", "africa", "nigeria", "emea"],
    "location_deny": ["us", "usa", "united states", "canada", "uk", "india"],
}


def test_generic_customer_support_specialist_does_not_match():
    assert not keep_job(make_job("Customer Support Specialist", "Worldwide"), CONFIG)


def test_technical_support_specialist_matches():
    job = make_job("Technical Support Specialist", "Worldwide")
    assert keep_job(job, CONFIG)
    assert job.location_status == "allowed"


def test_senior_roles_remain_eligible():
    for title in (
        "Senior IT Support Engineer",
        "Director of IT Support",
        "Head of IT Support",
        "VP of IT Support",
    ):
        assert keep_job(make_job(title, "Nigeria"), CONFIG)


def test_missing_and_anywhere_locations_remain_unknown():
    for location in ("", "Anywhere"):
        job = make_job("IT Support Engineer", location)
        assert keep_job(job, CONFIG)
        status, _ = assess_location(job, CONFIG)
        assert status == "unknown"
        assert job.location_status == "unknown"


def test_explicit_us_restrictions_in_title_or_description_are_rejected():
    title_job = make_job("US-based IT Support Engineer", "Worldwide")
    remote_job = make_job("US Remote Technical Support Advisor", "Anywhere in the World")
    description_job = make_job(
        "IT Support Engineer",
        "Worldwide",
        "Applicants must reside in the United States.",
    )
    assert not keep_job(title_job, CONFIG)
    assert not keep_job(remote_job, CONFIG)
    assert not keep_job(description_job, CONFIG)


def test_unknown_location_is_not_promoted_to_allowed():
    job = make_job("IT Support Engineer", "Ukraine")
    status, reason = assess_location(job, CONFIG)
    assert status == "unknown"
    assert "does not confirm eligibility" in reason
