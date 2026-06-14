"""Application domain models."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ApplicationStatus(str, Enum):
    """Status of a job application."""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApplicationPreview(BaseModel):
    """Preview shown to user before applying."""

    job_id: int
    company: str
    job_title: str
    match_score: int
    resume_path: str
    resume_filename: str
    missing_skills: List[str] = Field(default_factory=list)
    relevant_experience: List[str] = Field(default_factory=list)
    application_answers: Dict[str, str] = Field(default_factory=dict)
    tailored_summary: Optional[str] = None
    apply_url: str
    warnings: List[str] = Field(default_factory=list)


class Application(BaseModel):
    """Persisted application record."""

    id: int
    job_id: int
    resume_id: Optional[int] = None
    match_score: int
    status: ApplicationStatus
    resume_pdf_path: Optional[str] = None
    application_answers: Dict[str, Any] = Field(default_factory=dict)
    missing_skills: List[str] = Field(default_factory=list)
    relevant_experience: List[str] = Field(default_factory=list)
    match_analysis_json: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None


class ApplicationHistory(BaseModel):
    """Audit trail entry for application actions."""

    id: int
    application_id: int
    action: str
    details: Optional[str] = None
    performed_by: str = "system"
    created_at: datetime
