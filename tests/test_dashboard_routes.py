"""Tests for dashboard routes."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def api_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        yield client


@pytest.mark.asyncio
async def test_health_endpoint(api_client):
    response = await api_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "ollama" in data
    assert "migrations" in data


@pytest.mark.asyncio
async def test_dashboard_home(api_client):
    response = await api_client.get("/")
    assert response.status_code == 200
    assert "Dashboard" in response.text


@pytest.mark.asyncio
async def test_jobs_page(api_client):
    response = await api_client.get("/jobs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_recommended_page(api_client):
    response = await api_client.get("/recommended")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_resumes_page(api_client):
    response = await api_client.get("/resumes")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_applications_page(api_client):
    response = await api_client.get("/applications")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_discover_redirects_not_500(api_client, monkeypatch):
    async def fake_run_now():
        return {
            "success": False,
            "discovered_count": 0,
            "recommended_count": 0,
            "error": "test failure",
        }

    from app.container import get_container

    container = get_container()
    monkeypatch.setattr(container.scheduler, "run_now", fake_run_now)

    response = await api_client.post("/discover")
    assert response.status_code == 303
    assert "error=" in response.headers["location"]


@pytest.mark.asyncio
async def test_application_detail_404(api_client):
    response = await api_client.get("/applications/99999")
    assert response.status_code == 404
