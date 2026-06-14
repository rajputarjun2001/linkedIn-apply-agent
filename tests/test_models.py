"""Unit tests for resume models and validation."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.match import JobMatchResult
from app.models.resume import MasterResume, Skill, TailoredResume, WorkExperience


def test_job_match_result_coerces_experience_dicts():
    result = JobMatchResult.model_validate(
        {
            "match_score": 75,
            "relevant_experience": [
                {
                    "company": "Acme",
                    "title": "Developer",
                    "description": "Built APIs",
                }
            ],
        }
    )
    assert result.relevant_experience == ["Developer at Acme: Built APIs"]


def test_master_resume_valid():
    """Valid master resume should parse successfully."""
    resume = MasterResume(
        full_name="John Doe",
        email="john@example.com",
        skills=[Skill(name="Python")],
        work_experience=[
            WorkExperience(company="Acme", title="Developer"),
        ],
    )
    assert resume.full_name == "John Doe"
    assert len(resume.skills) == 1


def test_master_resume_requires_email():
    """Master resume must have valid email."""
    with pytest.raises(ValidationError):
        MasterResume(full_name="John", email="not-an-email")


def test_tailored_resume_extends_master():
    """Tailored resume includes tailoring metadata."""
    tailored = TailoredResume(
        full_name="John Doe",
        email="john@example.com",
        job_id=1,
        tailored_summary="Experienced Python developer.",
        skill_order=["Python"],
    )
    assert tailored.job_id == 1
    assert tailored.tailored_summary is not None


def test_skill_requires_name():
    """Skill name is required."""
    with pytest.raises(ValidationError):
        Skill(name="")


def test_work_experience_dates():
    """Work experience accepts optional dates."""
    exp = WorkExperience(
        company="TechCo",
        title="Engineer",
        start_date=date(2020, 1, 1),
        is_current=True,
    )
    assert exp.is_current is True
    assert exp.end_date is None
