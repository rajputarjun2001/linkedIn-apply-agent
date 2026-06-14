"""End-to-end workflow tests without external services."""

import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.agents.application_assistant import ApplicationAssistant
from app.agents.job_matcher import JobMatcher
from app.agents.resume_tailor import ResumeTailor
from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.models.job import Job, JobCreate, JobStatus
from app.models.match import JobMatchResult
from app.pdf.generator import PDFGenerator
from app.resume.manager import ResumeManager
from app.services.ollama_service import OllamaService


class MockOllama:
    async def generate_structured(self, prompt, model_class, **kwargs):
        if model_class.__name__ == "JobMatchResult":
            return JobMatchResult(
                match_score=88,
                missing_skills=["Kubernetes"],
                relevant_skills=["Python", "React"],
                relevant_experience=["TechCorp - Senior Full Stack Developer"],
                reasoning="Strong alignment with role requirements.",
                recommendation="apply",
            )
        raise RuntimeError("unexpected model")


class MockTailor(ResumeTailor):
    async def tailor(self, master, job):
        return self.tailor_without_ai(master, job)


@pytest.fixture
async def e2e_env(tmp_path):
    settings = Settings()
    settings.database_path = tmp_path / "e2e.db"
    settings.output_resumes_dir = tmp_path / "resumes"
    settings.master_resume_path = tmp_path / "master_resume.json"
    settings.min_match_score = 70

    db = DatabaseRepository(settings)
    await db.initialize()

    resume_manager = ResumeManager(settings)
    resume_manager.create_sample_resume()

    ollama = MockOllama()
    job_matcher = JobMatcher(ollama)  # type: ignore
    resume_tailor = MockTailor(OllamaService(settings))
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
        title="Senior Python Developer",
        company="RuntimeTest Corp",
        location="Remote",
        description="Python, React, FastAPI required.",
        apply_url="https://linkedin.com/jobs/view/e2e001",
        is_easy_apply=True,
    )
    job = await db.create_job(job_create)
    return {"settings": settings, "db": db, "assistant": assistant, "job": job}


@pytest.mark.asyncio
async def test_e2e_discover_match_tailor_pdf_approve_submit(e2e_env):
    assistant = e2e_env["assistant"]
    db = e2e_env["db"]
    job = e2e_env["job"]

    preview = await assistant.prepare_application(job)
    assert preview.match_score == 88
    assert preview.resume_path
    assert preview.missing_skills == ["Kubernetes"]

    updated_job = await db.get_job(job.id)
    assert updated_job.match_score == 88
    assert updated_job.missing_skills == ["Kubernetes"]
    assert updated_job.status == JobStatus.RECOMMENDED

    applications = await db.list_applications()
    assert len(applications) == 1
    app = applications[0]
    assert app.missing_skills == ["Kubernetes"]
    assert app.match_analysis_json["match_score"] == 88

    master_id = await db.get_master_resume_id()
    assert master_id is not None

    approved = await assistant.approve_application(app.id)
    assert approved.status.value == "approved"

    history = await db.get_application_history(app.id)
    assert any(h.action == "approved" for h in history)

    submitted = await assistant.mark_submitted(app.id, notes="Applied on LinkedIn")
    assert submitted.status.value == "submitted"

    history = await db.get_application_history(app.id)
    assert any(h.action == "submitted" for h in history)

    final_job = await db.get_job(job.id)
    assert final_job.status == JobStatus.APPLIED
