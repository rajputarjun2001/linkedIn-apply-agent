"""Job domain models."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Lifecycle status of a discovered job."""

    DISCOVERED = "discovered"
    MATCHED = "matched"
    RECOMMENDED = "recommended"
    APPLIED = "applied"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class JobCreate(BaseModel):
    """Input model for creating a job record."""

    title: str = Field(..., min_length=1)
    company: str = Field(..., min_length=1)
    location: str = Field(default="")
    description: str = Field(default="")
    apply_url: str = Field(..., min_length=1)
    posting_date: Optional[str] = None
    keyword: Optional[str] = None
    search_location: Optional[str] = None
    is_easy_apply: bool = True
    linkedin_job_id: Optional[str] = None


class Job(JobCreate):
    """Persisted job record."""

    id: int
    match_score: Optional[int] = None
    missing_skills: List[str] = Field(default_factory=list)
    relevant_skills: List[str] = Field(default_factory=list)
    relevant_experience: List[str] = Field(default_factory=list)
    match_reasoning: Optional[str] = None
    status: JobStatus = JobStatus.DISCOVERED
    created_at: datetime
    updated_at: datetime
