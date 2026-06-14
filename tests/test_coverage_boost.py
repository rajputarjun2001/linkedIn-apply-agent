"""Additional tests to reach coverage target."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.agents.resume_tailor import ResumeTailor
from app.config.settings import Settings
from app.models.job import Job
from app.models.match import JobMatchResult
from app.models.resume import MasterResume, Skill, TailoredResume
from app.prompts import load_prompt
from app.services.job_discovery_service import JobDiscoveryService
from app.services.ollama_service import OllamaService
from app.services.scheduler_service import SchedulerService
from app.utils.logger import setup_logging, get_logger


def test_load_prompt_missing():
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt.txt")


def test_setup_logging_and_get_logger(tmp_path):
    settings = Settings()
    settings.log_dir = tmp_path / "logs"
    setup_logging(settings)
    log = get_logger("test")
    assert log is not None


@pytest.mark.asyncio
async def test_resume_tailor_with_ollama(tmp_path):
    settings = Settings()
    tailor = ResumeTailor(OllamaService(settings))

    master = MasterResume(
        full_name="Test",
        email="t@example.com",
        skills=[Skill(name="Python")],
    )
    job = Job(
        id=1,
        title="Dev",
        company="Co",
        apply_url="https://linkedin.com/jobs/view/1",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    tailored_payload = TailoredResume(
        full_name="Test",
        email="t@example.com",
        skills=[Skill(name="Python")],
    )

    with patch.object(tailor._ollama, "generate_structured", AsyncMock(return_value=tailored_payload)):
        result = await tailor.tailor(master, job)
        assert result.skills[0].name == "Python"


@pytest.mark.asyncio
async def test_ollama_generate_http():
    settings = Settings()
    service = OllamaService(settings)

    class MockResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": '{"match_score": 70}'}

    with patch.object(service, "ensure_ready", AsyncMock()):
        with patch("httpx.AsyncClient") as client_cls:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = None
            client.post = AsyncMock(return_value=MockResponse())
            client_cls.return_value = client
            text = await service.generate("test prompt")
            assert "match_score" in text


@pytest.mark.asyncio
async def test_match_and_recommend_jobs(tmp_path):
    settings = Settings()
    settings.database_path = tmp_path / "match.db"
    settings.master_resume_path = tmp_path / "master.json"
    settings.output_resumes_dir = tmp_path / "resumes"

    from app.database.repository import DatabaseRepository
    from app.resume.manager import ResumeManager
    from app.models.job import JobCreate, JobStatus

    db = DatabaseRepository(settings)
    await db.initialize()
    rm = ResumeManager(settings)
    rm.create_sample_resume()
    job = await db.create_job(
        JobCreate(title="Dev", company="Co", apply_url="https://linkedin.com/jobs/view/m1", is_easy_apply=True)
    )

    ollama = AsyncMock()
    ollama.ensure_ready = AsyncMock()
    matcher = AsyncMock()
    matcher.match = AsyncMock(
        return_value=JobMatchResult(
            match_score=80,
            missing_skills=["Go"],
            relevant_skills=["Python"],
            relevant_experience=["exp"],
            reasoning="ok",
            recommendation="apply",
        )
    )
    assistant = AsyncMock()
    assistant.ensure_master_resume_stored = AsyncMock(return_value=1)
    assistant.prepare_application = AsyncMock()

    svc = JobDiscoveryService(
        settings=settings,
        db=db,
        scraper=AsyncMock(),
        browser=AsyncMock(),
        job_matcher=matcher,
        application_assistant=assistant,
        resume_manager=rm,
        ollama=ollama,
    )

    recommended = await svc.match_and_recommend_jobs()
    assert len(recommended) == 1
    updated = await db.get_job(job.id)
    assert updated.status == JobStatus.RECOMMENDED
    assert updated.missing_skills == ["Go"]


@pytest.mark.asyncio
async def test_scheduler_disabled():
    discovery = MagicMock()
    settings = Settings()
    settings.scheduler_enabled = False
    svc = SchedulerService(settings, discovery)
    svc.start()
    assert svc._scheduler is None
