"""LinkedIn browser tests with mocks."""

from unittest.mock import AsyncMock

import pytest

from app.config.settings import Settings
from app.linkedin.browser import LinkedInBrowser
from app.linkedin.errors import LinkedInNotConnectedError, LinkedInSessionExpiredError


@pytest.fixture
def browser(tmp_path):
    settings = Settings()
    settings.browser_session_path = tmp_path / "session"
    settings.base_dir = tmp_path
    return LinkedInBrowser(settings)


@pytest.mark.asyncio
async def test_ensure_authenticated_raises_when_disconnected(browser):
    with pytest.raises(LinkedInNotConnectedError):
        await browser.ensure_authenticated()


@pytest.mark.asyncio
async def test_ensure_authenticated_uses_valid_session(browser):
    browser._session_store.state_path.parent.mkdir(parents=True, exist_ok=True)
    browser._session_store.state_path.write_text('{"cookies": [{"name": "x"}]}', encoding="utf-8")
    browser.start = AsyncMock()
    browser.verify_session = AsyncMock(return_value=True)

    await browser.ensure_authenticated()
    browser.verify_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_authenticated_raises_when_expired(browser):
    browser._session_store.state_path.parent.mkdir(parents=True, exist_ok=True)
    browser._session_store.state_path.write_text('{"cookies": [{"name": "x"}]}', encoding="utf-8")
    browser.start = AsyncMock()
    browser.verify_session = AsyncMock(return_value=False)

    with pytest.raises(LinkedInSessionExpiredError):
        await browser.ensure_authenticated()


@pytest.mark.asyncio
async def test_close_handles_dead_context(browser):
    browser._context = AsyncMock()
    browser._context.close = AsyncMock()
    browser._context.storage_state = AsyncMock(side_effect=Exception("closed"))
    browser._browser = AsyncMock()
    browser._browser.close = AsyncMock()
    browser._playwright = AsyncMock()
    browser._playwright.stop = AsyncMock()
    await browser.close()
    assert browser._page is None


@pytest.mark.asyncio
async def test_recover_from_crash(browser):
    browser._session_store.state_path.parent.mkdir(parents=True, exist_ok=True)
    browser._session_store.state_path.write_text('{"cookies": [{"name": "x"}]}', encoding="utf-8")
    browser._start_unlocked = AsyncMock()
    browser.verify_session = AsyncMock(return_value=True)
    browser._close_unlocked = AsyncMock()
    await browser.recover_from_crash()
    browser._start_unlocked.assert_awaited_once_with(headless=True)


@pytest.mark.asyncio
async def test_recover_from_crash_raises_when_expired(browser):
    browser._session_store.state_path.parent.mkdir(parents=True, exist_ok=True)
    browser._session_store.state_path.write_text('{"cookies": [{"name": "x"}]}', encoding="utf-8")
    browser._start_unlocked = AsyncMock()
    browser.verify_session = AsyncMock(return_value=False)
    browser._close_unlocked = AsyncMock()

    with pytest.raises(LinkedInSessionExpiredError):
        await browser.recover_from_crash()
