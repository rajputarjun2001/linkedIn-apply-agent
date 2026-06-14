"""Job discovery progress tracking."""

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass
class DiscoveryProgress:
    """Live status for background discovery pipeline."""

    phase: str = "idle"
    message: str = ""
    current: int = 0
    total: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
