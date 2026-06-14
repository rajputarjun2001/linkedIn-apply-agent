"""Additional dashboard route tests."""

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
async def test_discover_success_redirect(api_client, monkeypatch):
    async def fake_run_now():
        return {
            "success": True,
            "discovered_count": 3,
            "recommended_count": 1,
            "error": None,
        }

    from app.container import get_container
    monkeypatch.setattr(get_container().scheduler, "run_now", fake_run_now)

    response = await api_client.post("/discover")
    assert response.status_code == 303
    assert "success=" in response.headers["location"]


@pytest.mark.asyncio
async def test_download_resume_404(api_client):
    response = await api_client.get("/resumes/download/99999")
    assert response.status_code == 404
