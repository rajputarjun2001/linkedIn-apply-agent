"""Tests for job discovery service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.settings import Settings
from app.models.job import JobCreate
from app.services.job_discovery_service import JobDiscoveryService
from app.services.ollama_service import OllamaUnavailableError


@pytest.fixture
def discovery_service():
    settings = Settings()
    db = AsyncMock()
    db.create_job = AsyncMock(side_effect=lambda j: MagicMock(id=1, title=j.title))
    browser = AsyncMock()
    browser.start = AsyncMock()
    browser.close = AsyncMock()
    browser.ensure_authenticated = AsyncMock()
    scraper = AsyncMock()
    scraper.search_all_configured = AsyncMock(
        return_value=[
            JobCreate(
                title="Dev",
                company="Co",
                apply_url="https://linkedin.com/jobs/view/1",
                is_easy_apply=True,
            )
        ]
    )
    ollama = AsyncMock()
    ollama.ensure_ready = AsyncMock()
    job_matcher = AsyncMock()
    assistant = AsyncMock()
    resume_manager = MagicMock()

    return JobDiscoveryService(
        settings=settings,
        db=db,
        scraper=scraper,
        browser=browser,
        job_matcher=job_matcher,
        application_assistant=assistant,
        resume_manager=resume_manager,
        ollama=ollama,
    )


@pytest.mark.asyncio
async def test_discover_jobs_stores_easy_apply(discovery_service):
    jobs = await discovery_service.discover_jobs()
    assert len(jobs) == 1
    discovery_service._browser.start.assert_awaited_once()
    discovery_service._browser.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_pipeline_success(discovery_service):
    discovery_service.discover_jobs = AsyncMock(return_value=[MagicMock()])
    discovery_service.match_and_recommend_jobs = AsyncMock(return_value=[MagicMock()])
    result = await discovery_service.run_full_pipeline()
    assert result["success"] is True


@pytest.mark.asyncio
async def test_pipeline_ollama_unavailable(discovery_service):
    discovery_service.discover_jobs = AsyncMock(side_effect=OllamaUnavailableError("down"))
    result = await discovery_service.run_full_pipeline()
    assert result["success"] is False
    assert "down" in result["error"]
