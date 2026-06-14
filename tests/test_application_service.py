"""Tests for application service and assistant edge cases."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.application_assistant import ApplicationAssistant
from app.config.settings import Settings
from app.models.application import ApplicationStatus
from app.services.application_service import ApplicationService


@pytest.fixture
def app_service():
    db = AsyncMock()
    assistant = AsyncMock()
    return ApplicationService(db=db, assistant=assistant, settings=Settings())


@pytest.mark.asyncio
async def test_get_pending_approvals(app_service):
    app_service._db.list_applications = AsyncMock(return_value=[])
    result = await app_service.get_pending_approvals()
    assert result == []


@pytest.mark.asyncio
async def test_approve_delegates(app_service):
    app_service._assistant.approve_application = AsyncMock(return_value=MagicMock())
    await app_service.approve(1, approved_by="user")
    app_service._assistant.approve_application.assert_awaited_once_with(1, "user")


@pytest.mark.asyncio
async def test_submit_delegates(app_service):
    app_service._assistant.mark_submitted = AsyncMock(return_value=MagicMock())
    await app_service.submit(1, notes="done")
    app_service._assistant.mark_submitted.assert_awaited_once_with(1, "user", "done")


@pytest.mark.asyncio
async def test_start_prepare_background(app_service):
    app_service._assistant.prepare_application = AsyncMock(return_value=MagicMock(job_title="Dev"))
    app_service._db.get_job = AsyncMock(return_value=MagicMock(id=1, title="Dev", company="Co"))
    app_service._db.list_applications = AsyncMock(return_value=[])

    result = app_service.start_prepare_background(1)
    assert result["started"] is True
    await app_service._prepare_task
    progress = app_service.prepare_progress(1)
    assert progress["completed"] is True


@pytest.mark.asyncio
async def test_reject_application_flow(tmp_path):
    from app.database.repository import DatabaseRepository
    from app.resume.manager import ResumeManager

    settings = Settings()
    settings.database_path = tmp_path / "reject.db"
    settings.master_resume_path = tmp_path / "master.json"
    settings.output_resumes_dir = tmp_path / "resumes"

    db = DatabaseRepository(settings)
    await db.initialize()

    resume_manager = ResumeManager(settings)
    resume_manager.create_sample_resume()

    from app.models.job import JobCreate

    job = await db.create_job(
        JobCreate(title="T", company="C", apply_url="https://linkedin.com/jobs/view/r1", is_easy_apply=True)
    )
    app = await db.create_application(job_id=job.id, match_score=80)

    assistant = ApplicationAssistant(
        settings=settings,
        db=db,
        resume_manager=resume_manager,
        job_matcher=AsyncMock(),
        resume_tailor=AsyncMock(),
        pdf_generator=MagicMock(),
    )

    rejected = await assistant.reject_application(app.id, reason="Not interested")
    assert rejected.status == ApplicationStatus.REJECTED
