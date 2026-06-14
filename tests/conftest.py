"""Shared pytest fixtures."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.config.settings import Settings
from app.database.repository import DatabaseRepository
from app.main import app


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings()
    s.database_path = tmp_path / "test.db"
    s.master_resume_path = tmp_path / "master_resume.json"
    s.output_resumes_dir = tmp_path / "resumes"
    s.browser_session_path = tmp_path / "browser_session"
    s.log_dir = tmp_path / "logs"
    return s


@pytest.fixture
async def db(settings):
    repository = DatabaseRepository(settings)
    await repository.initialize()
    return repository


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
