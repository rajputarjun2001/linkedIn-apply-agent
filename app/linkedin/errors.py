"""LinkedIn authentication errors."""

class LinkedInAuthError(RuntimeError):
    """Base LinkedIn authentication error."""


class LinkedInNotConnectedError(LinkedInAuthError):
    """No saved LinkedIn session exists."""

    def __init__(self) -> None:
        super().__init__(
            "LinkedIn is not connected. Click 'Connect LinkedIn' on the dashboard "
            "to sign in manually."
        )


class LinkedInSessionExpiredError(LinkedInAuthError):
    """Saved LinkedIn session is no longer valid."""

    def __init__(self) -> None:
        super().__init__(
            "LinkedIn session has expired. Click 'Connect LinkedIn' to sign in again."
        )


class LinkedInConnectTimeoutError(LinkedInAuthError):
    """User did not complete manual login in time."""

    def __init__(self, timeout_seconds: int) -> None:
        super().__init__(
            f"LinkedIn connect timed out after {timeout_seconds} seconds. "
            "Complete login in the browser window and try again."
        )
