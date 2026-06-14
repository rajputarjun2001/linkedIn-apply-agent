"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the AI Job Application Agent."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LinkedIn manual auth
    linkedin_connect_timeout: int = Field(default=300, alias="LINKEDIN_CONNECT_TIMEOUT", ge=60)

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.2", alias="OLLAMA_MODEL")
    ollama_timeout: int = Field(default=120, alias="OLLAMA_TIMEOUT")

    # Job search
    job_keywords: str = Field(
        default=(
            "Software Engineer,Frontend Developer,Backend Developer,"
            "Full Stack Developer,React Developer"
        ),
        alias="JOB_KEYWORDS",
    )
    locations: str = Field(default="United States,Remote", alias="LOCATIONS")
    min_match_score: int = Field(default=70, alias="MIN_MATCH_SCORE", ge=0, le=100)
    discovery_match_limit: int = Field(default=10, alias="DISCOVERY_MATCH_LIMIT", ge=1, le=50)

    # Scheduler
    scheduler_enabled: bool = Field(default=True, alias="SCHEDULER_ENABLED")
    scheduler_interval_hours: int = Field(default=1, alias="SCHEDULER_INTERVAL_HOURS", ge=1)

    # Paths
    base_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    database_path: Path = Field(default=Path("data/agent.db"))
    master_resume_path: Path = Field(default=Path("data/master_resume.json"))
    browser_session_path: Path = Field(default=Path("data/browser_session"))
    output_resumes_dir: Path = Field(default=Path("output/resumes"))
    log_dir: Path = Field(default=Path("logs"))

    # Server
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=False, alias="DEBUG")

    @field_validator("database_path", "master_resume_path", "browser_session_path", mode="before")
    @classmethod
    def resolve_relative_paths(cls, value: str | Path) -> Path:
        """Resolve relative paths against project root."""
        path = Path(value)
        if not path.is_absolute():
            root = Path(__file__).resolve().parents[2]
            return root / path
        return path

    @property
    def job_keyword_list(self) -> List[str]:
        """Return parsed job search keywords."""
        return [k.strip() for k in self.job_keywords.split(",") if k.strip()]

    @property
    def location_list(self) -> List[str]:
        """Return parsed job search locations."""
        return [loc.strip() for loc in self.locations.split(",") if loc.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
