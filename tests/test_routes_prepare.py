"""Additional route integration tests with database."""

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock

from app.main import app


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        yield client


@pytest.mark.asyncio
async def test_prepare_job_redirects_to_running_page(api_client, monkeypatch):
    from app.container import get_container
    from datetime import datetime
    from app.models.job import Job

    container = get_container()

    async def fake_get_job(job_id):
        return Job(
            id=job_id,
            title="T",
            company="C",
            apply_url=f"https://linkedin.com/jobs/view/p{job_id}",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

    monkeypatch.setattr(container.db, "get_job", fake_get_job)
    container.application_service._prepare_task = None

    response = await api_client.post("/jobs/1/prepare")
    assert response.status_code == 303
    assert response.headers["location"] == "/jobs/1/prepare/running"
