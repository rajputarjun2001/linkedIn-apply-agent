"""Deep LinkedIn browser tests for session-based auth."""

from unittest.mock import AsyncMock

import pytest

from app.config.settings import Settings
from app.linkedin.browser import LinkedInBrowser
from app.models.linkedin import LinkedInSessionStatus


@pytest.fixture
def browser(tmp_path):
    settings = Settings()
    settings.browser_session_path = tmp_path / "session"
    settings.base_dir = tmp_path
    return LinkedInBrowser(settings)


@pytest.mark.asyncio
async def test_save_session(browser):
    browser._context = AsyncMock()
    browser._context.storage_state = AsyncMock()
    await browser._save_session_unlocked()
    browser._context.storage_state.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_session_failure(browser):
    browser._page = AsyncMock()
    browser._page.url = "https://www.linkedin.com/login"
    browser._page.goto = AsyncMock()

    assert await browser.verify_session() is False
    assert browser.is_authenticated is False


@pytest.mark.asyncio
async def test_url_indicates_checkpoint(browser):
    assert browser._url_indicates_logged_in("https://www.linkedin.com/checkpoint/challenge") is False


@pytest.mark.asyncio
async def test_get_status_connected_with_verify(browser):
    browser._session_store.state_path.parent.mkdir(parents=True, exist_ok=True)
    browser._session_store.state_path.write_text('{"cookies": [{"name": "x"}]}', encoding="utf-8")
    browser.start = AsyncMock()
    browser.verify_session = AsyncMock(return_value=True)
    browser._close_unlocked = AsyncMock()

    status = await browser.get_status(verify=True)
    assert status == LinkedInSessionStatus.CONNECTED
