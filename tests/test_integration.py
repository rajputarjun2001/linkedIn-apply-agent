"""Integration tests for application approval workflow."""

import pytest
from datetime import datetime

from app.agents.application_assistant import ApplicationAssistant
from app.agents.job_matcher import JobMatcher
from app.agents.resume_tailor import ResumeTailor
from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.models.application import ApplicationStatus
from app.models.job import Job, JobCreate, JobStatus
from app.models.match import JobMatchResult
from app.pdf.generator import PDFGenerator
from app.resume.manager import ResumeManager
from app.services.ollama_service import OllamaService


class MockOllamaService:
    """Mock Ollama for integration tests without LLM."""

    async def generate_structured(self, prompt, model_class, **kwargs):
        if model_class.__name__ == "JobMatchResult":
            return JobMatchResult(
                match_score=85,
                missing_skills=["Kubernetes"],
                relevant_skills=["Python", "React"],
                relevant_experience=["Corp - Developer: Built APIs"],
                reasoning="Strong match for Python role.",
                recommendation="apply",
            )
        raise NotImplementedError("Use fallback tailor for tests")


class MockResumeTailor(ResumeTailor):
    """Resume tailor that uses deterministic fallback (no Ollama)."""

    async def tailor(self, master, job):
        return self.tailor_without_ai(master, job)


@pytest.fixture
async def integration_setup(tmp_path):
    """Set up full integration test environment."""
    settings = Settings()
    settings.database_path = tmp_path / "integration.db"
    settings.output_resumes_dir = tmp_path / "resumes"
    settings.master_resume_path = tmp_path / "master_resume.json"
    settings.min_match_score = 70

    db = DatabaseRepository(settings)
    await db.initialize()

    resume_manager = ResumeManager(settings)
    resume_manager.create_sample_resume()

    ollama = MockOllamaService()
    job_matcher = JobMatcher(ollama)  # type: ignore
    resume_tailor = MockResumeTailor(OllamaService(settings))
    pdf_generator = PDFGenerator(settings)

    assistant = ApplicationAssistant(
        settings=settings,
        db=db,
        resume_manager=resume_manager,
        job_matcher=job_matcher,
        resume_tailor=resume_tailor,
        pdf_generator=pdf_generator,
    )

    job_create = JobCreate(
        title="Full Stack Developer",
        company="IntegrationCorp",
        location="Remote",
        description="Python and React developer needed.",
        apply_url="https://linkedin.com/jobs/view/integration1",
        is_easy_apply=True,
    )
    job = await db.create_job(job_create)

    return {
        "settings": settings,
        "db": db,
        "assistant": assistant,
        "job": job,
    }


@pytest.mark.asyncio
async def test_full_approval_workflow(integration_setup):
    """Test prepare -> approve -> submit workflow."""
    assistant = integration_setup["assistant"]
    db = integration_setup["db"]
    job = integration_setup["job"]

    preview = await assistant.prepare_application(job)
    assert preview.match_score == 85
    assert preview.resume_path

    applications = await db.list_applications(status=ApplicationStatus.PENDING_APPROVAL)
    assert len(applications) == 1
    app_id = applications[0].id

    approved = await assistant.approve_application(app_id)
    assert approved.status == ApplicationStatus.APPROVED

    submitted = await assistant.mark_submitted(app_id, notes="Applied manually on LinkedIn")
    assert submitted.status == ApplicationStatus.SUBMITTED

    updated_job = await db.get_job(job.id)
    assert updated_job.status == JobStatus.APPLIED


@pytest.mark.asyncio
async def test_cannot_approve_below_threshold(integration_setup):
    """Applications below match threshold cannot be approved."""
    assistant = integration_setup["assistant"]
    db = integration_setup["db"]

    job_create = JobCreate(
        title="Low Match Job",
        company="Corp",
        apply_url="https://linkedin.com/jobs/view/lowmatch",
        is_easy_apply=True,
    )
    job = await db.create_job(job_create)

    application = await db.create_application(job_id=job.id, match_score=50)

    with pytest.raises(ValueError, match="below threshold"):
        await assistant.approve_application(application.id)


@pytest.mark.asyncio
async def test_cannot_submit_without_approval(integration_setup):
    """Submission requires prior approval."""
    assistant = integration_setup["assistant"]
    db = integration_setup["db"]
    job = integration_setup["job"]

    application = await db.create_application(job_id=job.id, match_score=80)

    with pytest.raises(ValueError, match="must be approved"):
        await assistant.mark_submitted(application.id)
