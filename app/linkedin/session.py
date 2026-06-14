"""LinkedIn browser session helpers."""

from pathlib import Path
from typing import Optional

from loguru import logger

SESSION_FILENAME = "linkedin_state.json"


class SessionStore:
    """Manages persisted Playwright storage state (no credentials)."""

    def __init__(self, session_dir: Path) -> None:
        self._session_dir = session_dir
        self._state_file = session_dir / SESSION_FILENAME

    @property
    def state_path(self) -> Path:
        return self._state_file

    def exists(self) -> bool:
        """Return True when a saved session file exists."""
        return self._state_file.exists() and self._state_file.stat().st_size > 10

    def load_path(self) -> Optional[str]:
        """Return storage state path for Playwright if available."""
        if self.exists():
            logger.bind(component="linkedin_session").info(
                "Loading saved session from {}", self._state_file
            )
            return str(self._state_file)
        return None

    def clear(self) -> None:
        """Remove saved session."""
        if self._state_file.exists():
            self._state_file.unlink()
            logger.bind(component="linkedin_session").info("Cleared LinkedIn session")
