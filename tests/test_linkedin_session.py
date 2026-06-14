"""Tests for LinkedIn manual session authentication."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.config.settings import Settings
from app.linkedin.browser import LinkedInBrowser
from app.linkedin.errors import LinkedInNotConnectedError, LinkedInSessionExpiredError
from app.linkedin.session import SESSION_FILENAME, SessionStore
from app.models.linkedin import LinkedInSessionStatus
from app.services.linkedin_auth_service import LinkedInAuthService


@pytest.fixture
def settings(tmp_path):
    s = Settings()
    s.browser_session_path = tmp_path / "session"
    return s


@pytest.fixture
def browser(settings):
    return LinkedInBrowser(settings)


@pytest.fixture
def auth_service(settings, browser):
    return LinkedInAuthService(settings, browser)


def _write_session(path, cookies=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"cookies": cookies or [{"name": "li_at", "value": "x"}]}),
        encoding="utf-8",
    )


def test_session_filename():
    assert SESSION_FILENAME == "linkedin_state.json"


def test_session_save_path(settings):
    store = SessionStore(settings.browser_session_path)
    _write_session(store.state_path)
    assert store.exists() is True
    assert store.state_path.name == "linkedin_state.json"


def test_session_load_path(settings):
    store = SessionStore(settings.browser_session_path)
    assert store.load_path() is None
    _write_session(store.state_path)
    assert store.load_path() == str(store.state_path)


def test_session_clear(settings):
    store = SessionStore(settings.browser_session_path)
    _write_session(store.state_path)
    store.clear()
    assert store.exists() is False


@pytest.mark.asyncio
async def test_get_status_disconnected(browser):
    status = await browser.get_status(verify=False)
    assert status == LinkedInSessionStatus.DISCONNECTED


@pytest.mark.asyncio
async def test_get_status_connected_without_verify(browser, settings):
    _write_session(browser.session_store.state_path)
    status = await browser.get_status(verify=False)
    assert status == LinkedInSessionStatus.CONNECTED


@pytest.mark.asyncio
async def test_get_status_expired(browser, settings):
    _write_session(browser.session_store.state_path)
    browser.start = AsyncMock()
    browser.verify_session = AsyncMock(return_value=False)
    browser._close_unlocked = AsyncMock()

    status = await browser.get_status(verify=True)
    assert status == LinkedInSessionStatus.EXPIRED


@pytest.mark.asyncio
async def test_ensure_authenticated_not_connected(browser):
    with pytest.raises(LinkedInNotConnectedError):
        await browser.ensure_authenticated()


@pytest.mark.asyncio
async def test_ensure_authenticated_expired(browser, settings):
    _write_session(browser.session_store.state_path)
    browser.start = AsyncMock()
    browser.verify_session = AsyncMock(return_value=False)

    with pytest.raises(LinkedInSessionExpiredError):
        await browser.ensure_authenticated()


@pytest.mark.asyncio
async def test_disconnect_flow(browser, settings):
    _write_session(browser.session_store.state_path)
    browser._close_unlocked = AsyncMock()

    await browser.disconnect()

    assert browser.session_store.exists() is False
    assert browser.is_authenticated is False
    browser._close_unlocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_interactive_saves_session(browser):
    page = AsyncMock()
    page.url = "https://www.linkedin.com/feed/"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()

    browser._start_unlocked = AsyncMock()
    browser._page = page
    browser._context = AsyncMock()
    browser._context.storage_state = AsyncMock()
    browser._close_unlocked = AsyncMock()

    with patch("app.linkedin.browser.asyncio.sleep", new=AsyncMock()):
        await browser.connect_interactive(timeout_seconds=10)

    browser._start_unlocked.assert_awaited_once_with(headless=False)
    browser._context.storage_state.assert_awaited_once()
    browser._close_unlocked.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_service_disconnect(auth_service, browser):
    browser.disconnect = AsyncMock()
    await auth_service.disconnect()
    browser.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_service_status_payload(auth_service, browser):
    browser.get_status = AsyncMock(return_value=LinkedInSessionStatus.CONNECTED)
    browser.session_store.exists = lambda: True

    result = await auth_service.status(verify=True)
    assert result["status"] == "connected"
    assert result["label"] == "Connected"
    assert result["session_exists"] is True


@pytest.mark.asyncio
async def test_start_connect_background(auth_service):
    auth_service._browser.connect_interactive = AsyncMock()
    result = auth_service.start_connect_background()
    assert result["started"] is True
    assert result["in_progress"] is True
    auth_service._connect_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await auth_service._connect_task


def test_connect_progress_idle(auth_service):
    progress = auth_service.connect_progress()
    assert progress["in_progress"] is False
    assert progress["completed"] is False
