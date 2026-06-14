"""Playwright browser session management for LinkedIn (manual login only)."""

import asyncio
from pathlib import Path
from typing import Optional

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.config.settings import Settings
from app.linkedin.errors import (
    LinkedInConnectTimeoutError,
    LinkedInNotConnectedError,
    LinkedInSessionExpiredError,
)
from app.linkedin.session import SessionStore
from app.models.linkedin import LinkedInSessionStatus

LOGGED_IN_URL_MARKERS = (
    "/feed",
    "/mynetwork",
    "/jobs",
    "/in/",
    "linkedin.com/hp",
)
LOGIN_URL = "https://www.linkedin.com/login/"
FEED_URL = "https://www.linkedin.com/feed/"


class LinkedInBrowser:
    """Manages LinkedIn sessions via Playwright storage state — no credentials."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._session_store = SessionStore(settings.browser_session_path)
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._authenticated = False
        self._lock = asyncio.Lock()

    @property
    def session_store(self) -> SessionStore:
        return self._session_store

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def page(self) -> Page:
        if not self._page:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def _url_indicates_logged_in(self, url: str) -> bool:
        lowered = url.lower()
        if "login" in lowered or "checkpoint" in lowered or "challenge" in lowered:
            return False
        return any(marker in lowered for marker in LOGGED_IN_URL_MARKERS)

    async def start(self, headless: bool = True) -> None:
        """Start browser with saved session if available."""
        async with self._lock:
            await self._start_unlocked(headless=headless)

    async def _start_unlocked(self, headless: bool = True) -> None:
        """Start browser without acquiring lock (caller must hold lock if needed)."""
        self._session_store.state_path.parent.mkdir(parents=True, exist_ok=True)
        if self._playwright:
            await self._close_unlocked()

        self._playwright = await async_playwright().start()
        launch_args = ["--disable-blink-features=AutomationControlled"]
        if not headless:
            launch_args.extend(["--start-maximized", "--window-position=0,0"])
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=launch_args,
        )
        self._context = await self._browser.new_context(
            storage_state=self._session_store.load_path(),
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._context.set_default_timeout(45000)
        self._page = await self._context.new_page()
        logger.bind(component="linkedin_browser").info(
            "Browser started (headless={})", headless
        )

    async def verify_session(self) -> bool:
        """Verify saved session is still valid by visiting the feed."""
        if not self._page:
            raise RuntimeError("Browser not started")

        page = self.page
        try:
            await page.goto(FEED_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(2)
            if self._url_indicates_logged_in(page.url):
                self._authenticated = True
                logger.bind(component="linkedin_browser").info(
                    "Session valid at {}", page.url
                )
                return True
            logger.bind(component="linkedin_browser").info(
                "Session invalid, redirected to {}", page.url
            )
            self._authenticated = False
            return False
        except Exception as exc:
            logger.bind(component="linkedin_browser").warning(
                "Session verification failed: {}", exc
            )
            self._authenticated = False
            return False

    async def connect_interactive(self, timeout_seconds: int = 300) -> None:
        """
        Launch headed browser for manual LinkedIn login.

        User completes login, CAPTCHA, and 2FA manually. Polls until feed is detected,
        then saves storage state and closes the browser.
        """
        async with self._lock:
            await self._start_unlocked(headless=False)
            page = self.page

            logger.bind(component="linkedin_browser").info(
                "Opening LinkedIn login for manual authentication"
            )
            try:
                await page.goto(LOGIN_URL, wait_until="commit", timeout=30000)
            except Exception as exc:
                logger.bind(component="linkedin_browser").warning(
                    "LinkedIn login navigation slow or interrupted: {} — continue in browser window",
                    exc,
                )
            logger.bind(component="linkedin_browser").info(
                "LinkedIn login window ready at {}", page.url
            )

            elapsed = 0
            poll_interval = 2
            while elapsed < timeout_seconds:
                current_url = page.url
                if self._url_indicates_logged_in(current_url):
                    await self._save_session_unlocked()
                    self._authenticated = True
                    logger.bind(component="linkedin_browser").info(
                        "Manual login successful, session saved"
                    )
                    await self._close_unlocked()
                    return

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

            await self._close_unlocked()
            raise LinkedInConnectTimeoutError(timeout_seconds)

    async def disconnect(self) -> None:
        """Clear saved session and reset authentication state."""
        async with self._lock:
            await self._close_unlocked()
            self._session_store.clear()
            self._authenticated = False
            logger.bind(component="linkedin_browser").info("LinkedIn disconnected")

    async def get_status(self, verify: bool = True) -> LinkedInSessionStatus:
        """Return current LinkedIn session status."""
        if not self._session_store.exists():
            return LinkedInSessionStatus.DISCONNECTED

        if not verify:
            return LinkedInSessionStatus.CONNECTED

        try:
            await self.start(headless=True)
            valid = await self.verify_session()
            await self._close_unlocked()
            return (
                LinkedInSessionStatus.CONNECTED
                if valid
                else LinkedInSessionStatus.EXPIRED
            )
        except Exception as exc:
            logger.bind(component="linkedin_browser").warning(
                "Status check failed: {}", exc
            )
            await self._close_unlocked()
            return LinkedInSessionStatus.EXPIRED

    async def ensure_authenticated(self) -> None:
        """Ensure a valid LinkedIn session exists for automated workflows."""
        if not self._session_store.exists():
            raise LinkedInNotConnectedError()

        if not self._page:
            await self.start(headless=True)

        if await self.verify_session():
            return

        raise LinkedInSessionExpiredError()

    async def _save_session_unlocked(self) -> None:
        """Persist browser session to linkedin_state.json."""
        if not self._context:
            return
        try:
            await self._context.storage_state(path=str(self._session_store.state_path))
            logger.bind(component="linkedin_browser").debug(
                "Session saved to {}", self._session_store.state_path
            )
        except Exception as exc:
            logger.bind(component="linkedin_browser").warning(
                "Could not save session: {}", exc
            )

    async def save_session(self) -> None:
        async with self._lock:
            await self._save_session_unlocked()

    async def recover_from_crash(self) -> None:
        """Restart browser and re-verify saved session."""
        async with self._lock:
            logger.bind(component="linkedin_browser").warning(
                "Recovering from browser crash"
            )
            await self._close_unlocked()
            await self._start_unlocked(headless=True)
            if self._session_store.exists():
                self._authenticated = await self.verify_session()
            if not self._authenticated:
                raise LinkedInSessionExpiredError()

    async def _close_unlocked(self) -> None:
        """Close browser without acquiring lock."""
        try:
            if self._context:
                try:
                    if self._authenticated:
                        await self._save_session_unlocked()
                except Exception:
                    pass
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as exc:
            logger.bind(component="linkedin_browser").error(
                "Error closing browser: {}", exc
            )
        finally:
            self._playwright = None
            self._browser = None
            self._context = None
            self._page = None

    async def close(self) -> None:
        """Close browser and cleanup resources."""
        async with self._lock:
            await self._close_unlocked()
