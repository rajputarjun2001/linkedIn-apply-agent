"""Unit tests for resume tailoring anti-fabrication safeguards."""

from datetime import date

import pytest

from app.agents.resume_tailor import ResumeFabricationError, ResumeTailor
from app.models.job import Job
from app.models.resume import MasterResume, Project, Skill, TailoredResume, WorkExperience
from app.services.ollama_service import OllamaService
from app.config.settings import Settings


@pytest.fixture
def master_resume() -> MasterResume:
    return MasterResume(
        full_name="Test User",
        email="test@example.com",
        skills=[Skill(name="Python"), Skill(name="React")],
        projects=[Project(name="MyApp", description="A web app", technologies=["Python"])],
        work_experience=[
            WorkExperience(company="Corp", title="Developer", start_date=date(2020, 1, 1)),
        ],
    )


@pytest.fixture
def sample_job() -> Job:
    from datetime import datetime

    return Job(
        id=1,
        title="Python Developer",
        company="TechCorp",
        location="Remote",
        description="Looking for Python and React developers.",
        apply_url="https://linkedin.com/jobs/view/123",
        is_easy_apply=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def resume_tailor() -> ResumeTailor:
    settings = Settings()
    return ResumeTailor(OllamaService(settings))


def test_fallback_tailor_no_fabrication(resume_tailor, master_resume, sample_job):
    """Fallback tailor only reorders existing content."""
    tailored = resume_tailor.tailor_without_ai(master_resume, sample_job)

    assert len(tailored.skills) == len(master_resume.skills)
    assert {s.name for s in tailored.skills} == {s.name for s in master_resume.skills}
    assert len(tailored.projects) == len(master_resume.projects)
    assert tailored.job_id == sample_job.id


def test_fabrication_detection(resume_tailor, master_resume):
    """Fabricated skills should be detected."""
    fabricated = TailoredResume(
        full_name=master_resume.full_name,
        email=master_resume.email,
        skills=[Skill(name="Kubernetes")],  # Not in master resume
        projects=master_resume.projects,
        work_experience=master_resume.work_experience,
    )

    with pytest.raises(ResumeFabricationError):
        resume_tailor._validate_no_fabrication(master_resume, fabricated)


def test_valid_tailored_passes_validation(resume_tailor, master_resume):
    """Tailored resume with only master content passes validation."""
    tailored = TailoredResume(
        full_name=master_resume.full_name,
        email=master_resume.email,
        skills=list(reversed(master_resume.skills)),
        projects=master_resume.projects,
        work_experience=master_resume.work_experience,
    )

    resume_tailor._validate_no_fabrication(master_resume, tailored)
