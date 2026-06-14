"""Tests for scheduler service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config.settings import Settings
from app.services.scheduler_service import SchedulerService


@pytest.fixture
def scheduler():
    discovery = MagicMock()
    discovery.run_full_pipeline = AsyncMock(
        return_value={"success": True, "discovered_count": 2, "recommended_count": 1}
    )
    return SchedulerService(Settings(scheduler_enabled=False), discovery)


@pytest.mark.asyncio
async def test_run_now_returns_pipeline_result(scheduler):
    result = await scheduler.run_now()
    assert result["success"] is True
    assert result["discovered_count"] == 2


@pytest.mark.asyncio
async def test_scheduled_job_logs_failure(scheduler):
    scheduler._job_discovery.run_full_pipeline = AsyncMock(
        return_value={"success": False, "discovered_count": 0, "recommended_count": 0, "error": "fail"}
    )
    await scheduler._run_discovery_job()


@pytest.mark.asyncio
async def test_start_discovery_background(scheduler):
    result = scheduler.start_discovery_background()
    assert result["started"] is True
    assert result["in_progress"] is True
    await scheduler._discovery_task
    progress = scheduler.discovery_progress()
    assert progress["completed"] is True
    assert progress["success"] is True


@pytest.mark.asyncio
async def test_discovery_progress_idle(scheduler):
    progress = scheduler.discovery_progress()
    assert progress["in_progress"] is False
    assert progress["completed"] is False
