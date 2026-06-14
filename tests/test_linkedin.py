"""Tests for LinkedIn browser and scraper."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config.settings import Settings
from app.linkedin.browser import LinkedInBrowser
from app.linkedin.scraper import LinkedInScraper
from app.linkedin.session import SessionStore
from app.models.job import JobCreate


@pytest.fixture
def linkedin_settings(tmp_path):
    s = Settings()
    s.browser_session_path = tmp_path / "session"
    s.base_dir = tmp_path
    return s


def test_session_store_detects_existing(tmp_path):
    store = SessionStore(tmp_path / "session")
    store.state_path.parent.mkdir(parents=True)
    store.state_path.write_text('{"cookies": []}', encoding="utf-8")
    assert store.exists() is True


def test_session_store_missing(tmp_path):
    store = SessionStore(tmp_path / "session")
    assert store.exists() is False


def test_build_search_url_has_easy_apply_filter(linkedin_settings):
    scraper = LinkedInScraper(linkedin_settings, MagicMock())
    url = scraper._build_search_url("Python Developer", "India")
    assert "f_AL=true" in url
    assert "Python" in url


def test_extract_job_id():
    job_id = LinkedInScraper._extract_job_id("https://www.linkedin.com/jobs/view/1234567890")
    assert job_id == "1234567890"


@pytest.mark.asyncio
async def test_url_indicates_logged_in(linkedin_settings):
    browser = LinkedInBrowser(linkedin_settings)
    assert browser._url_indicates_logged_in("https://www.linkedin.com/feed/") is True
    assert browser._url_indicates_logged_in("https://www.linkedin.com/login") is False


@pytest.mark.asyncio
async def test_verify_session_success(linkedin_settings):
    browser = LinkedInBrowser(linkedin_settings)
    browser._authenticated = False
    browser._page = AsyncMock()
    browser._page.url = "https://www.linkedin.com/feed/"
    browser._page.goto = AsyncMock()
    browser._save_session_unlocked = AsyncMock()

    assert await browser.verify_session() is True
    assert browser.is_authenticated is True


@pytest.mark.asyncio
async def test_scraper_saves_job_samples(linkedin_settings, tmp_path):
    linkedin_settings.base_dir = tmp_path
    scraper = LinkedInScraper(linkedin_settings, MagicMock())
    jobs = [
        JobCreate(
            title="Engineer",
            company="Corp",
            apply_url="https://linkedin.com/jobs/view/1",
            is_easy_apply=True,
        )
    ]
    scraper._save_job_samples(jobs, "Engineer", "India")
    samples = list((tmp_path / "output" / "job_samples").glob("*.json"))
    assert len(samples) == 1
