import json
from pathlib import Path

import pytest

from remote_job_tracker.models import Job
from remote_job_tracker.models import make_job as build_job
from remote_job_tracker.scoring import score_job

CONFIG = {
    "location_allow": ["worldwide", "africa", "nigeria", "emea"],
    "location_deny": ["us", "usa", "united states", "canada", "uk", "india"],
    "profile": {
        "skills": ["Windows", "Linux", "networking", "SQL", "Python", "Excel", "Docker", "Git"],
        "primary_roles": ["IT support", "technical support", "service desk"],
        "secondary_roles": ["data analyst", "DevOps"],
        "seniority_stretch_terms": ["senior"],
        "high_stretch_terms": ["lead", "director", "head", "vp"],
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


def make_job(title: str, description: str, location: str) -> Job:
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


def test_full_skill_and_primary_role_match_scores_100():
    job = make_job(
        "IT Support Engineer",
        "Windows Linux networking SQL Python Excel Docker Git",
        "Nigeria",
    )
    result = score_job(job, CONFIG)
    assert result.score == 100
    assert len(result.reasons) == 4
    assert all("points." in reason for reason in result.reasons)
    assert job.fit_score == 100
    assert job.score_reasons == list(result.reasons)


def test_unknown_location_is_visible_and_scores_below_allowed():
    job = make_job("IT Support Engineer", "Linux Python support experience", "Anywhere")
    result = score_job(job, CONFIG)
    assert result.score < 100
    assert "unknown location - 5/15 points" in result.reasons[2]
    assert job.location_status == "unknown"


def test_secondary_role_has_lower_role_points_than_primary_role():
    primary = score_job(
        make_job("IT Support Engineer", "Linux", "Nigeria"), CONFIG
    )
    secondary = score_job(make_job("Data Analyst", "Linux", "Nigeria"), CONFIG)
    assert primary.score > secondary.score
    assert "25/25 points" in primary.reasons[1]
    assert "18/25 points" in secondary.reasons[1]


def test_seniority_stretch_reduces_score_without_excluding_job():
    standard = score_job(make_job("IT Support Engineer", "Linux", "Nigeria"), CONFIG)
    senior = score_job(make_job("Senior IT Support Engineer", "Linux", "Nigeria"), CONFIG)
    director = score_job(make_job("Director of IT Support", "Linux", "Nigeria"), CONFIG)
    assert standard.score - senior.score == 4
    assert standard.score - director.score == 7
    assert "seniority stretch" in senior.reasons[3]
    assert "high stretch" in director.reasons[3]


def test_invalid_empty_profile_skills_are_rejected():
    config = {**CONFIG, "profile": {**CONFIG["profile"], "skills": []}}
    with pytest.raises(ValueError, match="at least one skill"):
        score_job(make_job("IT Support Engineer", "Linux", "Nigeria"), config)


def test_invalid_score_weights_are_rejected():
    config = {**CONFIG, "score_weights": {**CONFIG["score_weights"], "role": "high"}}
    with pytest.raises(ValueError, match="must be an integer"):
        score_job(make_job("IT Support Engineer", "Linux", "Nigeria"), config)


def test_aliases_match_and_are_explained():
    config = {
        **CONFIG,
        "profile": {
            **CONFIG["profile"],
            "skills": ["help desk"],
            "skill_aliases": {"help desk": ["helpdesk", "service desk"]},
        },
    }
    job = make_job("Service Desk Engineer", "Contact the helpdesk team.", "Nigeria")
    result = score_job(job, config)
    assert result.score == 100
    assert "help desk (matched 'helpdesk')" in result.reasons[0]
    service_desk_result = score_job(
        make_job("Service Desk Engineer", "", "Nigeria"), config
    )
    assert "help desk (matched 'service desk')" in service_desk_result.reasons[0]


def test_skills_match_after_previous_description_truncation_boundary():
    description = "General support information. " * 250 + "Hands-on Power BI reporting."
    job = build_job(
        "remotive",
        "long-description",
        "IT Support Engineer",
        "Example Co",
        "Nigeria",
        "https://example.com/job",
        "",
        description,
    )
    config = {
        **CONFIG,
        "profile": {
            **CONFIG["profile"],
            "skills": ["Power BI"],
            "skill_aliases": {"Power BI": ["PowerBI"]},
        },
    }
    result = score_job(job, config)
    assert len(job.description) > 4000
    assert result.score == 100
    assert "Power BI" in result.reasons[0]


def test_config_contains_user_approved_profile_skills():
    config = json.loads((Path(__file__).parents[1] / "config.json").read_text())
    assert config["profile"]["skills"] == [
        "Windows 10",
        "Windows 11",
        "troubleshooting",
        "hardware",
        "printer",
        "networking",
        "TCP/IP",
        "DNS",
        "DHCP",
        "Wi-Fi",
        "VPN",
        "Microsoft 365",
        "Outlook",
        "Teams",
        "OneDrive",
        "Active Directory",
        "Entra ID",
        "MFA",
        "ticketing",
        "incident management",
        "root cause analysis",
        "remote support",
        "remote desktop",
        "patching",
        "documentation",
        "knowledge base",
        "customer service",
        "cybersecurity",
        "endpoint protection",
        "access control",
        "backup",
        "PowerShell",
        "asset inventory",
        "SLA",
        "Linux",
        "command line",
        "SQL",
        "Python",
        "JavaScript",
        "HTML",
        "CSS",
        "Excel",
        "Power BI",
        "Git",
        "GitHub",
        "Docker",
        "cloud",
    ]
