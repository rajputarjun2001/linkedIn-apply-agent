"""LinkedIn manual authentication service."""

import asyncio
from typing import Any, Dict, Optional

from loguru import logger

from app.config.settings import Settings
from app.linkedin.browser import LinkedInBrowser
from app.linkedin.errors import LinkedInAuthError
from app.models.linkedin import LinkedInSessionStatus


class LinkedInAuthService:
    """Coordinates manual LinkedIn connect/disconnect and status checks."""

    def __init__(self, settings: Settings, browser: LinkedInBrowser) -> None:
        self._settings = settings
        self._browser = browser
        self._connect_task: Optional[asyncio.Task] = None
        self._connect_error: Optional[str] = None

    async def connect(self) -> LinkedInSessionStatus:
        """Launch headed browser for manual login and save session."""
        await self._browser.connect_interactive(
            timeout_seconds=self._settings.linkedin_connect_timeout
        )
        return LinkedInSessionStatus.CONNECTED

    def start_connect_background(self) -> Dict[str, Any]:
        """Start manual LinkedIn login without blocking the HTTP request."""
        if self._connect_task and not self._connect_task.done():
            return {
                "started": False,
                "in_progress": True,
                "message": "LinkedIn connect is already in progress.",
            }

        self._connect_error = None
        self._connect_task = asyncio.create_task(
            self._run_connect(),
            name="linkedin_connect",
        )
        return {
            "started": True,
            "in_progress": True,
            "message": "Opening LinkedIn login window...",
        }

    async def _run_connect(self) -> None:
        try:
            await self.connect()
            logger.bind(component="linkedin_auth").info("Background LinkedIn connect succeeded")
        except LinkedInAuthError as exc:
            self._connect_error = str(exc)
            logger.bind(component="linkedin_auth").warning(
                "Background LinkedIn connect failed: {}", exc
            )
        except Exception as exc:
            self._connect_error = str(exc)
            logger.bind(component="linkedin_auth").error(
                "Background LinkedIn connect failed: {}", exc
            )

    def connect_progress(self) -> Dict[str, Any]:
        """Return background connect task state for polling."""
        if self._connect_task is None:
            return {
                "in_progress": False,
                "completed": False,
                "success": False,
                "error": self._connect_error,
            }

        if not self._connect_task.done():
            return {
                "in_progress": True,
                "completed": False,
                "success": False,
                "error": None,
            }

        success = self._connect_task.exception() is None and self._connect_error is None
        if not success and self._connect_error is None and self._connect_task.exception():
            self._connect_error = str(self._connect_task.exception())

        return {
            "in_progress": False,
            "completed": True,
            "success": success,
            "error": self._connect_error,
        }

    async def disconnect(self) -> None:
        """Clear saved LinkedIn session."""
        await self._browser.disconnect()

    async def status(self, verify: bool = True) -> Dict[str, Any]:
        """Return LinkedIn connection status for API and dashboard."""
        session_status = await self._browser.get_status(verify=verify)
        return {
            "status": session_status.value,
            "label": session_status.label,
            "session_file": str(self._browser.session_store.state_path),
            "session_exists": self._browser.session_store.exists(),
        }
