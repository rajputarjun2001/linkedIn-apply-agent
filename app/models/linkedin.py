"""LinkedIn session status models."""

from enum import Enum


class LinkedInSessionStatus(str, Enum):
    """LinkedIn authentication session state."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"

    @property
    def label(self) -> str:
        return {
            LinkedInSessionStatus.CONNECTED: "Connected",
            LinkedInSessionStatus.DISCONNECTED: "Disconnected",
            LinkedInSessionStatus.EXPIRED: "Session Expired",
        }[self]
