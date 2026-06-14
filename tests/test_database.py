"""Unit tests for database repository."""

import pytest
from datetime import datetime

from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.models.application import ApplicationStatus
from app.models.job import JobCreate, JobStatus
from app.models.match import JobMatchResult


@pytest.fixture
async def db(tmp_path):
    """Create isolated test database."""
    settings = Settings()
    settings.database_path = tmp_path / "test.db"
    repository = DatabaseRepository(settings)
    await repository.initialize()
    return repository


@pytest.mark.asyncio
async def test_create_and_get_job(db):
    """Jobs can be created and retrieved."""
    job_create = JobCreate(
        title="Software Engineer",
        company="TestCorp",
        location="Remote",
        description="Build software.",
        apply_url="https://linkedin.com/jobs/view/999",
        is_easy_apply=True,
        linkedin_job_id="999",
    )
    created = await db.create_job(job_create)
    assert created is not None
    assert created.title == "Software Engineer"

    fetched = await db.get_job(created.id)
    assert fetched is not None
    assert fetched.company == "TestCorp"


@pytest.mark.asyncio
async def test_duplicate_job_prevention(db):
    """Duplicate jobs by apply_url are rejected."""
    job_create = JobCreate(
        title="Engineer",
        company="Corp",
        apply_url="https://linkedin.com/jobs/view/100",
        is_easy_apply=True,
    )
    first = await db.create_job(job_create)
    second = await db.create_job(job_create)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_update_job_match(db):
    """Job match score can be updated."""
    job_create = JobCreate(
        title="Developer",
        company="Corp",
        apply_url="https://linkedin.com/jobs/view/101",
        is_easy_apply=True,
    )
    job = await db.create_job(job_create)
    await db.update_job_match(job.id, 85, JobStatus.RECOMMENDED, match_result=JobMatchResult(
        match_score=85,
        missing_skills=[],
        relevant_skills=["Python"],
        relevant_experience=["Experience"],
        reasoning="test",
        recommendation="apply",
    ))

    updated = await db.get_job(job.id)
    assert updated.match_score == 85
    assert updated.status == JobStatus.RECOMMENDED


@pytest.mark.asyncio
async def test_create_application(db):
    """Applications can be created with pending approval status."""
    job_create = JobCreate(
        title="Developer",
        company="Corp",
        apply_url="https://linkedin.com/jobs/view/102",
        is_easy_apply=True,
    )
    job = await db.create_job(job_create)

    application = await db.create_application(
        job_id=job.id,
        match_score=80,
        resume_pdf_path="/tmp/resume.pdf",
    )

    assert application.status == ApplicationStatus.PENDING_APPROVAL
    assert application.match_score == 80


@pytest.mark.asyncio
async def test_duplicate_application_prevention(db):
    """Only one application per job is allowed."""
    job_create = JobCreate(
        title="Developer",
        company="Corp",
        apply_url="https://linkedin.com/jobs/view/103",
        is_easy_apply=True,
    )
    job = await db.create_job(job_create)
    await db.create_application(job_id=job.id, match_score=75)

    with pytest.raises(ValueError, match="already exists"):
        await db.create_application(job_id=job.id, match_score=75)


@pytest.mark.asyncio
async def test_statistics(db):
    """Statistics endpoint returns counts."""
    job_create = JobCreate(
        title="Developer",
        company="Corp",
        apply_url="https://linkedin.com/jobs/view/104",
        is_easy_apply=True,
    )
    await db.create_job(job_create)

    stats = await db.get_statistics()
    assert stats["total_jobs"] >= 1
